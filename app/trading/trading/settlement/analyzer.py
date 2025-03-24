"""交易分析器

负责解析交易的具体内容，包括：
1. 分析交易输入输出
2. 计算实际的交易数量
3. 提取其他重要的交易信息
"""

from typing import TypedDict

from solbot_common.constants import SOL_DECIMAL, WSOL
# from solbot_common.utils.helius import HeliusAPI
from solbot_common.utils.shyft import ShyftAPI
from solbot_common.config import settings
from solbot_cache.token_info import TokenInfoCache

from datetime import datetime, timezone


class Result(TypedDict):
    fee: int
    slot: int
    timestamp: int
    sol_change: float
    swap_sol_change: float
    other_sol_change: float
    token_change: float


class TransactionAnalyzer:
    """交易分析器"""

    def __init__(self) -> None:
        # self.helius_api = HeliusAPI()
        self.shyft_api = ShyftAPI()
        self.token_info_cache = TokenInfoCache()

    async def analyze_transaction(self, tx_signature: str, user_account: str, mint: str) -> Result:
        """分析交易详情

        Args:
            tx_signature: 交易签名
        """
        # 获取交易详情
        tx_details = await self.shyft_api.get_parsed_transaction(tx_signature)
        if tx_details is None:
            raise Exception("交易不存在")
        fee = tx_details['fee']
        slot = 0
        timestamp = int(datetime.strptime(tx_details["timestamp"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc).timestamp())
        # PREF: ADD PUMP SELL
        # 测试金额累计是否正确
        tx_type = tx_details['type']
        if tx_type == "SWAP":
            swap_sol_change = None
            token_change = None

            for action in tx_details['actions']:
                # PREF: setting wallet is not updated.
                if 'swapper' in action['info'] and action['info']['swapper'] == settings.wallet.pubkey:
                    if action['info']['tokens_swapped']['in']['token_address'] == str(WSOL):
                        swap_sol_change = float(action['info']['tokens_swapped']['in']['amount'])
                        token_change = float(action['info']['tokens_swapped']['out']['amount'])
                    else:
                        assert action['info']['tokens_swapped']['out']['token_address'] == str(WSOL)
                        swap_sol_change = float(action['info']['tokens_swapped']['out']['amount'])
                        token_change = float(action['info']['tokens_swapped']['in']['amount'])
                    break

            assert swap_sol_change is not None and token_change is not None, f"Sol or Token change is None: {settings.wallet.pubkey}"
            return {
                "fee": fee,
                "slot": slot,
                "timestamp": timestamp,
                "sol_change": fee + swap_sol_change,
                "swap_sol_change": swap_sol_change,
                "other_sol_change": fee,
                "token_change": token_change,
            }
        # 假设出现问题
        elif tx_type in ["TOKEN_TRANSFER", "SELL"]:
            assert len(tx_details['events']) == 1 and tx_details['events'][0]['name'] == 'SwapEvent', f"Error Tx Parsed: {tx_details['events']}"
            swap_event = tx_details['events'][0]
            swap_sol_change = None
            token_change = None
            if swap_event['data']['input_mint'] == str(WSOL):
                swap_sol_change = swap_event['data']['input_amount'] / 10 ** SOL_DECIMAL
                token_change = swap_event['data']['output_amount'] / 10 ** (await self.token_info_cache.get(swap_event['data']['output_mint'])).decimals
            elif swap_event['data']['output_mint'] == str(WSOL):
                swap_sol_change = swap_event['data']['output_amount'] / 10 ** SOL_DECIMAL
                token_change = swap_event['data']['input_amount'] / 10 ** (await self.token_info_cache.get(swap_event['data']['input_mint'])).decimals
            else:
                raise ValueError("Input & Output mint both not SOL.")
            
            return {
                "fee": fee,
                "slot": slot,
                "timestamp": timestamp,
                "sol_change": swap_sol_change + fee,
                "swap_sol_change": swap_sol_change,
                "other_sol_change": fee,
                "token_change": token_change,
            }
        else:
            raise NotImplementedError(f"不支持的交易类型: {tx_type}")
        


    # async def analyze_transaction(self, tx_signature: str, user_account: str, mint: str) -> Result:
    #     """分析交易详情

    #     Args:
    #         tx_signature: 交易签名
    #     """
    #     # 获取交易详情
    #     tx_details = await self.helius_api.get_parsed_transaction(tx_signature)
    #     if len(tx_details) == 0:
    #         raise Exception("交易不存在")
    #     tx_detail = tx_details[0]
    #     fee = tx_detail["fee"]
    #     slot = tx_detail["slot"]
    #     timestamp = tx_detail["timestamp"]
    #     tx_type = tx_detail["type"]
    #     if tx_type != "SWAP":
    #         confirm_swap = await self.shyft_api.is_transaction_swap(tx_signature)
    #         if not confirm_swap:
    #             raise NotImplementedError(f"不支持的交易类型: {tx_type}")
    #         else:
    #             tx_type = "SWAP"

    #     sol_change = 0
    #     token_change = 0
    #     swap_sol_change = 0
    #     token_transfers = tx_detail["tokenTransfers"]
    #     for token_transfer in token_transfers:
    #         # Buy
    #         if token_transfer["fromUserAccount"] == user_account and token_transfer["mint"] == str(
    #             WSOL
    #         ):
    #             # sol_change -= token_transfer["tokenAmount"]
    #             swap_sol_change -= token_transfer["tokenAmount"]
    #         if token_transfer["toUserAccount"] == user_account and token_transfer["mint"] == mint:
    #             token_change += token_transfer["tokenAmount"]
    #         # Sell
    #         if (
    #             token_transfer["fromUserAccount"] == user_account and token_transfer["mint"] == mint
    #         ):
    #             token_change -= token_transfer["tokenAmount"]
    #         if token_transfer["toUserAccount"] == user_account and token_transfer["mint"] == str(
    #             WSOL
    #         ):
    #             # sol_change += token_transfer["tokenAmount"]
    #             swap_sol_change += token_transfer["tokenAmount"]

    #     for native_transfer in tx_detail["nativeTransfers"]:
    #         if native_transfer["fromUserAccount"] == user_account:
    #             sol_change -= native_transfer["amount"] / 10 ** SOL_DECIMAL
    #         elif native_transfer["toUserAccount"] == user_account:
    #             sol_change += native_transfer["amount"] / 10 ** SOL_DECIMAL

    #     return {
    #         "fee": fee,
    #         "slot": slot,
    #         "timestamp": timestamp,
    #         "sol_change": sol_change,
    #         "swap_sol_change": swap_sol_change,
    #         "other_sol_change": sol_change - swap_sol_change,
    #         "token_change": token_change,
    #     }

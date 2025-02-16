"""交易分析器

负责解析交易的具体内容，包括：
1. 分析交易输入输出
2. 计算实际的交易数量
3. 提取其他重要的交易信息
"""

from typing import TypedDict

from common.constants import SOL_DECIMAL, WSOL
from common.utils.helius import HeliusAPI
from common.utils.shyft import ShyftAPI
from common.log import logger

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
        self.helius_api = HeliusAPI()
        self.shyft_api = ShyftAPI()


    async def analyze_transaction(
        self, tx_signature: str, user_account: str, mint: str
    ) -> Result:
        """分析交易详情

        Args:
            tx_signature: 交易签名
        """
        # 获取交易详情
        tx_details = await self.helius_api.get_parsed_transaction(tx_signature)
        if len(tx_details) == 0:
            raise Exception("交易不存在")
        tx_detail = tx_details[0]
        fee = tx_detail["fee"]
        slot = tx_detail["slot"]
        timestamp = tx_detail["timestamp"]
        tx_type = tx_detail["type"]
        logger.info("1")
        if tx_type != "SWAP":
            logger.warning(f"不支持的交易类型: {tx_type}, 使用 Shyft API 进行确认...")
            confirm_swap = await self.shyft_api.is_transaction_swap(tx_signature)
            if not confirm_swap:
                raise NotImplementedError(f"双重确认完成，发现不支持的交易类型: {tx_type}.")
            else:
                tx_type = "SWAP"
                logger.warning(f"使用 Shyft API 确认完成，交易类型：SWAP.")

        sol_change = 0
        token_change = 0
        swap_sol_change = 0
        token_transfers = tx_detail["tokenTransfers"]
        logger.info("2")
        for token_transfer in token_transfers:
            # Buy
            if token_transfer["fromUserAccount"] == user_account and token_transfer[
                "mint"
            ] == str(WSOL):
                sol_change -= token_transfer["tokenAmount"]
                swap_sol_change -= token_transfer["tokenAmount"]
            elif (
                token_transfer["toUserAccount"] == user_account
                and token_transfer["mint"] == mint
            ):
                token_change += token_transfer["tokenAmount"]
            # Sell
            elif (
                token_transfer["fromUserAccount"] == user_account
                and token_transfer["mint"] == mint
            ):
                token_change -= token_transfer["tokenAmount"]
            elif token_transfer["toUserAccount"] == user_account and token_transfer[
                "mint"
            ] == str(WSOL):
                sol_change += token_transfer["tokenAmount"]
                swap_sol_change += token_transfer["tokenAmount"]
        logger.info("3")
        for native_transfer in tx_detail["nativeTransfers"]:
            if native_transfer["fromUserAccount"] == user_account:
                sol_change -= native_transfer["amount"] / 10 ** SOL_DECIMAL
            elif native_transfer["toUserAccount"] == user_account:
                sol_change += native_transfer["amount"] / 10 ** SOL_DECIMAL
        logger.info("4")
        return {
            "fee": fee,
            "slot": slot,
            "timestamp": timestamp,
            "sol_change": sol_change,
            "swap_sol_change": swap_sol_change,
            "other_sol_change": sol_change - swap_sol_change,
            "token_change": token_change,
        }

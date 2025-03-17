"""交易验证器

交易验证器用于验证交易的上链情况.
"""

import asyncio

from solbot_common.constants import SOL_DECIMAL
from solbot_common.log import logger
from solbot_common.models.swap_record import SwapRecord, TransactionStatus
from solbot_common.types.swap import SwapEvent
from solbot_common.types.enums import SwapDirection
from solbot_common.utils.utils import validate_transaction
from solbot_db.session import NEW_ASYNC_SESSION, provide_session
from solbot_cache.token_info import TokenInfoCache
from solders.signature import Signature  # type: ignore

from .analyzer import TransactionAnalyzer


class SwapSettlementProcessor:
    """Swap交易结算处理器

    验证交易结果并写入数据库
    """

    def __init__(self):
        self.analyzer = TransactionAnalyzer()
        self.token_info_cache = TokenInfoCache()

    @provide_session
    async def record(
        self,
        swap_event: SwapRecord,
        *,
        session=NEW_ASYNC_SESSION,
    ):
        """记录交易信息"""
        session.add(swap_event)
        await session.commit()

    async def validate(self, tx_hash: Signature) -> TransactionStatus | None:
        """验证交易是否已经上链.

        调用 validate 会返回一个协程，协程会在 60 秒内等待交易的上链状态。
        如果协程超时，则返回 None。

        Examples:
            >>> from solders.signature import Signature  # type: ignore
            >>> from solbot_common.models.swap_record import TransactionStatus
            >>> tx_hash = Signature.from_string("4uTy6e7h2SyxuwMyGsJ2Mxh3Rrj99CFeQ6uF1H8xFsEzW8xfrUZ9Xb8QxYutd5zt2cutP45CSPX3CypMAc3ykr2q")
            >>> status = await validator.validate(tx_hash)
            >>> if status == TransactionStatus.SUCCESS:
            ...     print("交易已经上链")
            ... elif status == TransactionStatus.FAILED:
            ...     print("交易失败")
            ... elif status == TransactionStatus.EXPIRED:
            ...     print("交易超时")
            ... else:
            ...     print("交易未知状态")

        Args:
            tx_hash (Signature): 交易 hash

        Returns:
            Coroutine[None, None, TransactionStatus | None]: 协程
        """
        tx_status = None
        for _ in range(60):
            try:
                tx_status = await validate_transaction(tx_hash)
            except Exception as e:
                logger.error(f"Failed to get transaction status: {e}")
                await asyncio.sleep(1)
                continue

            if tx_status is True:
                return TransactionStatus.SUCCESS
            elif tx_status is False:
                return TransactionStatus.FAILED
            await asyncio.sleep(1)
        return TransactionStatus.EXPIRED

    async def process(self, signature: Signature | None, swap_event: SwapEvent) -> SwapRecord:
        """处理交易

        Args:
            swap_event (SwapRecord): 交易记录
        """
        input_amount = swap_event.amount
        input_mint = swap_event.input_mint
        output_mint = swap_event.output_mint

        # 手动卖出时无tx_event，需要手动设置decimals
        if swap_event.tx_event:
            input_token_decimals = swap_event.tx_event.from_decimals
            output_token_decimals = swap_event.tx_event.to_decimals
        elif swap_event.swap_direction == SwapDirection.Buy:
            input_token_decimals = 9
            token_info = await self.token_info_cache.get(output_mint)
            output_token_decimals = token_info.decimals
        else:
            token_info = await self.token_info_cache.get(input_mint)
            input_token_decimals = token_info.decimals
            output_token_decimals = 9

        if signature is None:
            swap_record = SwapRecord(
                user_pubkey=swap_event.user_pubkey,
                swap_diretcion=swap_event.swap_direction,
                input_mint=swap_event.input_mint,
                output_mint=swap_event.output_mint,
                input_amount=swap_event.amount,
                input_token_decimals=input_token_decimals,
                output_amount=swap_event.amount,
                output_token_decimals=output_token_decimals,
            )
        else:
            tx_status = await self.validate(signature)
            # PREF: 在此考虑是否重新提交交易。
            if tx_status != TransactionStatus.SUCCESS:
                swap_record = SwapRecord(
                    signature=str(signature),
                    status=tx_status,
                    user_pubkey=swap_event.user_pubkey,
                    swap_direction=swap_event.swap_direction,
                    input_mint=swap_event.input_mint,
                    output_mint=swap_event.output_mint,
                    input_amount=swap_event.amount,
                    input_token_decimals=input_token_decimals,
                    output_amount=swap_event.amount,
                    output_token_decimals=output_token_decimals,
                )
            else:
                data = await self.analyzer.analyze_transaction(
                    str(signature),
                    user_account=swap_event.user_pubkey,
                    mint=swap_event.output_mint,
                )
                logger.debug(f"Transaction analysis data: {data}")

                if swap_event.swap_direction == SwapDirection.Buy:
                    output_amount = int(abs(data["token_change"]) * 10 ** output_token_decimals)
                else:
                    output_amount = int(abs(data["swap_sol_change"]) * 10 ** SOL_DECIMAL)

                swap_record = SwapRecord(
                    signature=str(signature),
                    status=tx_status,
                    user_pubkey=swap_event.user_pubkey,
                    swap_direction=swap_event.swap_direction,
                    input_mint=input_mint,
                    output_mint=output_mint,
                    input_amount=input_amount,
                    input_token_decimals=input_token_decimals,
                    output_amount=output_amount,
                    output_token_decimals=output_token_decimals,
                    program_id=swap_event.program_id,
                    timestamp=swap_event.timestamp,
                    fee=data["fee"],
                    slot=data["slot"],
                    sol_change=int(data["sol_change"] * 10 ** SOL_DECIMAL),
                    swap_sol_change=int(data["swap_sol_change"] * 10 ** SOL_DECIMAL),
                    other_sol_change=int(data["other_sol_change"] * 10 ** SOL_DECIMAL),
                )

        swap_record_clone = swap_record.model_copy()
        await self.record(swap_record)
        return swap_record_clone

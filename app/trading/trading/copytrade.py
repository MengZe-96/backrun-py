"""跟单交易

订阅 tx_event 事件，并将其转为 swap_event 事件
"""

import asyncio
from typing import Literal

from solbot_common.constants import WSOL
from solbot_common.cp.copytrade_event import NotifyCopyTradeProducer
from solbot_common.cp.swap_event import SwapEventProducer
from solbot_common.cp.tx_event import TxEventConsumer
from solbot_common.log import logger
from solbot_common.models.tg_bot.copytrade import CopyTrade
from solbot_common.types.swap import SwapEvent
from solbot_common.types.enums import SwapDirection
from solbot_common.types.tx import TxEvent, TxType
from solbot_common.utils import calculate_auto_slippage
from solbot_db.redis import RedisClient
from solbot_services.bot_setting import BotSettingService as SettingService
from solbot_services.copytrade import CopyTradeService
from solbot_services.holding import HoldingService

IGNORED_MINTS = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",  # mSOL
}


class CopyTradeProcessor:
    """跟单交易"""

    def __init__(self):
        redis_client = RedisClient.get_instance()
        self.tx_event_consumer = TxEventConsumer(
            redis_client,
            "trading:tx_event",
            "trading:new_swap_event",
        )
        self.tx_event_consumer.register_callback(self._process_tx_event)
        self.copytrade_service = CopyTradeService()
        self.setting_service = SettingService()
        self.swap_event_producer = SwapEventProducer(redis_client)
        self.notify_copytrade_producer = NotifyCopyTradeProducer(redis_client)

    async def _process_tx_event(self, tx_event: TxEvent):
        """处理交易事件"""
        logger.info(f"Processing tx event: {tx_event}")
        copytrade_items = await self.copytrade_service.get_by_target_wallet(tx_event.who)
        sell_pct = 0
        if tx_event.tx_direction == SwapDirection.Buy:
            input_mint = WSOL.__str__()
            output_mint = tx_event.mint
        else:
            input_mint = tx_event.mint
            output_mint = WSOL.__str__()
            # 卖出比例
            if tx_event.tx_type == TxType.CLOSE_POSITION:
                sell_pct = 1
            else:
                sell_pct = round(
                    (tx_event.pre_token_amount - tx_event.post_token_amount)
                    / tx_event.pre_token_amount,
                    4,
                )
                # 如果卖出比例大于95%，则全部卖出，处理留尾巴
                sell_pct = 1 if sell_pct > 0.95 else sell_pct
        program_id = tx_event.program_id
        timestamp = tx_event.timestamp

        tasks = []
        for copytrade in copytrade_items:
            coro = self._process_copytrade(
                swap_direction=tx_event.tx_direction,
                tx_event=tx_event,
                program_id=program_id,
                sell_pct=sell_pct,
                input_mint=input_mint,
                output_mint=output_mint,
                timestamp=timestamp,
                copytrade=copytrade,
            )
            tasks.append(coro)

        await asyncio.gather(*tasks)

    async def _process_copytrade(
        self,
        swap_direction: SwapDirection,
        tx_event: TxEvent,
        program_id: str | None,
        sell_pct: float,
        input_mint: str,
        output_mint: str,
        timestamp: int,
        copytrade: CopyTrade,
    ):
        if input_mint in IGNORED_MINTS or output_mint in IGNORED_MINTS:
            logger.info(f"Skipping swap due to ignored mint: {input_mint} {output_mint}")
            return

        try:
            # 根据不同的根据设置，创建不同的 swap_event
            setting = await self.setting_service.get(copytrade.chat_id, copytrade.owner)
            if setting is None:
                raise ValueError(
                    f"Setting not found, chat_id: {copytrade.chat_id}, wallet: {copytrade.owner}"
                )

            if swap_direction == SwapDirection.Buy:
                if copytrade.auto_buy:
                    amount = tx_event.from_amount * copytrade.auto_buy_ratio
                    amount = min(copytrade.max_buy_sol, amount)
                    amount = int(max(copytrade.min_buy_sol, amount))
                    ui_amount = amount / 10 ** tx_event.from_decimals
                else:
                    logger.info("Not auto buy, skip...")
                    return
            else:
                if copytrade.auto_sell:
                    # 数据库获取token balance
                    holding = await HoldingService.get_positions(
                        target_wallets=[tx_event.who], mint=input_mint, mode=3
                    )
                    if holding is None:
                        logger.info(f"No holdings for {tx_event.mint}, skip...")
                        return

                    my_amount = holding.my_amount

                    if my_amount <= 0:
                        logger.info(f"No holdings for {tx_event.mint}, skip...")
                        return

                    amount = int(my_amount * sell_pct)
                    ui_amount = amount / 10 ** holding.decimals
                else:
                    logger.info("Not auto sell, skip...")
                    return

            if copytrade.anti_sandwich:
                slippage_bps = setting.sandwich_slippage_bps
            elif copytrade.auto_slippage is False:
                slippage_bps = copytrade.custom_slippage * 100
            else:
                slippage_bps = await calculate_auto_slippage(
                    input_mint=input_mint,
                    output_mint=output_mint,
                    amount=amount,
                    swap_mode="ExactIn",
                )

            if swap_direction == SwapDirection.Sell:
                amount_pct = sell_pct
                swap_in_type = "pct"
            else:
                amount_pct = None
                swap_in_type = "qty"

            priority_fee = copytrade.priority / 10 ** 9
            swap_event = SwapEvent(
                user_pubkey=copytrade.owner,
                swap_direction=swap_direction,
                input_mint=input_mint,
                output_mint=output_mint,
                amount=amount,
                ui_amount=ui_amount,
                slippage_bps=slippage_bps,
                timestamp=timestamp,
                priority_fee=priority_fee,
                program_id=program_id,
                amount_pct=amount_pct,
                swap_in_type=swap_in_type,
                by="copytrade",
                tx_event=tx_event,
            )
            # PERF: 理论上,这两个 producer 是重复的
            # 只需要在 consumer 处, 使用不同的消费组即可
            await self.swap_event_producer.produce(swap_event=swap_event)
            await self.notify_copytrade_producer.produce(data=swap_event)
            logger.info(f"New Copy Trade: {swap_event}")
        except Exception as e:
            logger.exception(f"Failed to process copytrade: {e}")
            # TODO: 通知到用户，跟单交易失败

    async def start(self):
        """启动跟单交易"""
        await self.tx_event_consumer.start()

    def stop(self):
        """停止跟单交易"""
        self.tx_event_consumer.stop()

import asyncio

import aioredis
from aiogram import Bot

from cache.token_info import TokenInfoCache
from common.cp.copytrade_event import NotifyCopyTradeConsumer
from common.log import logger
from common.types.swap import SwapEvent
from tg_bot.services.copytrade import CopyTradeService
from tg_bot.services.user import UserService

__BUY_TEMPLATE = """
🎯 触发跟单：买入
{target_wallet} {wallet_alias} 买入 ${symbol} {amount} SOL

{mint}
"""


__SELL_TEMPLATE = """
🎯 触发跟单：卖出
{target_wallet} {wallet_alias} 卖出 {amount} ${symbol}

{mint}
"""


class CopyTradeNotify:
    """跟单通知"""

    def __init__(
        self,
        redis: aioredis.Redis,
        bot: Bot,
        batch_size: int = 10,
        poll_timeout_ms: int = 5000,
    ):
        self.redis = redis
        self.bot = bot
        self.consumer = NotifyCopyTradeConsumer(
            redis_client=redis,
            consumer_group="notify_copytrade",
            consumer_name="notify_copytrade",
            batch_size=batch_size,
            poll_timeout_ms=poll_timeout_ms,
        )
        # Register the callback
        self.consumer.register_callback(self._handle_event)
        self.user_service = UserService()
        self.copytrade_service = CopyTradeService()
        self.token_info_cache = TokenInfoCache()

    async def _build_message(self, data: SwapEvent, chat_id: int) -> str:
        """构建消息"""
        if data.by != "copytrade":
            raise ValueError("Invalid by")

        if data.tx_event is None:
            raise ValueError("tx_event is None")

        tx_event = data.tx_event
        template = __SELL_TEMPLATE
        amount = tx_event.from_decimals

        token_info = await self.token_info_cache.get(tx_event.mint)
        if token_info is None:
            logger.warning(f"Failed to get token info: {tx_event.mint}")
            token_symbol = "Unknown"
        else:
            token_symbol = token_info.symbol

        wallet_alias = await self.copytrade_service.get_wallet_alias(
            target_wallet=tx_event.who,
            chat_id=chat_id,
        )

        return template.format(
            target_wallet=tx_event.who,
            wallet_alias=wallet_alias if wallet_alias else "Unknown",
            symbol=token_symbol,
            amount=amount,
            mint=tx_event.mint,
        )

    async def _handle_event(self, data: SwapEvent):
        """处理交易事件"""
        chat_ids = await self.user_service.get_chat_id_by_pubkey(data.user_pubkey)

        tasks = []
        for chat_id in chat_ids:
            message = await self._build_message(data, chat_id)

            tasks.append(self.bot_service.send_message(chat_id, data.message))

    async def start(self):
        """启动跟单通知"""
        await asyncio.create_task(self.consumer.start())

    def stop(self):
        """停止跟单通知"""
        self.consumer.stop()

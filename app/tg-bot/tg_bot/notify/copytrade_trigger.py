import asyncio

import aioredis
from aiogram import Bot
from aiogram.types import LinkPreviewOptions
from jinja2 import BaseLoader, Environment
from solbot_cache.token_info import TokenInfoCache
from solbot_common.cp.copytrade_event import NotifyCopyTradeConsumer
from solbot_common.log import logger
from solbot_common.types.swap import SwapEvent
from solbot_common.types.enums import SwapDirection

from tg_bot.services.copytrade import CopyTradeService
from tg_bot.services.user import UserService
from tg_bot.utils.text import short_text

env = Environment(
    loader=BaseLoader(),
)
_BUY_TEMPLATE = env.from_string(
    """🎯 触发跟单：买入
🟢 {{wallet_name}} 买入 {{token_ui_amount}} ${{symbol}}

钱包地址
<code>{{wallet_address}}</code>
代币地址
<code>{{mint}}</code>
<a href="https://solscan.io/tx/{{signature}}">查看交易</a>
"""
)


_SELL_TEMPLATE = env.from_string(
    """🎯 触发跟单：卖出
🔴 {{wallet_name}} 卖出 {{token_ui_amount}} ${{symbol}}

钱包地址
<code>{{wallet_address}}</code>
代币地址
<code>{{mint}}</code>
<a href="https://solscan.io/tx/{{signature}}">查看交易</a>
"""
)


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
            consumer_group="copytrade_notify",
            consumer_name="copytrade_notify",
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
        if tx_event.tx_direction == SwapDirection.Buy:
            template = _BUY_TEMPLATE
            sol_ui_amount = tx_event.from_amount / (10**tx_event.from_decimals)
            token_ui_amount = tx_event.to_amount / (10**tx_event.to_decimals)
        elif tx_event.tx_direction == SwapDirection.Sell:
            template = _SELL_TEMPLATE
            token_ui_amount = tx_event.from_amount / (10**tx_event.from_decimals)
            sol_ui_amount = tx_event.to_amount / (10**tx_event.to_decimals)
        else:
            raise ValueError("Invalid by")

        token_info = await self.token_info_cache.get(tx_event.mint)
        if token_info is None:
            logger.warning(f"Failed to get token info: {tx_event.mint}")
            token_symbol = "Unknown"
        else:
            token_symbol = token_info.symbol

        target_alias = await self.copytrade_service.get_target_alias(
            target_wallet=tx_event.who,
            chat_id=chat_id,
        )

        return template.render(
            wallet_address=tx_event.who,
            wallet_name=target_alias if target_alias else short_text(tx_event.who),
            symbol=token_symbol,
            sol_ui_amount=sol_ui_amount,
            token_ui_amount=token_ui_amount,
            mint=tx_event.mint,
            signature=tx_event.signature,
        )

    async def _handle_event(self, data: SwapEvent):
        """处理交易事件"""
        chat_ids = await self.user_service.get_chat_id_by_pubkey(data.user_pubkey)

        tasks = []
        for chat_id in chat_ids:
            message = await self._build_message(data, chat_id)
            tasks.append(
                self.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode="HTML",
                    link_preview_options=LinkPreviewOptions(
                        is_disabled=True,
                    ),
                )
            )

        await asyncio.gather(*tasks)

    async def start(self):
        """启动跟单通知"""
        # 创建任务但不等待它完成
        consumer_task = asyncio.create_task(self.consumer.start())
        # 添加任务完成回调以处理可能的异常
        consumer_task.add_done_callback(lambda t: t.exception() if t.exception() else None)

    def stop(self):
        """停止跟单通知"""
        self.consumer.stop()

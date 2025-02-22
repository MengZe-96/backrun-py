import asyncio

from aiogram.types import LinkPreviewOptions
import aioredis
from aiogram import Bot
from aiogram.enums import ParseMode
from jinja2 import BaseLoader, Environment

from cache.token_info import TokenInfoCache
from common.cp.swap_result import SwapResultConsumer
from common.log import logger
from common.models.swap_record import TransactionStatus
from common.types.swap import SwapResult
from common.types.enums import SwapDirection
from tg_bot.services.user import UserService


env = Environment(
    loader=BaseLoader(),
)

_BUY_SUCCESS_TEMPLATE = env.from_string(
    """✅ 购买成功
├ 买入 {{token_ui_amount}} ${{symbol}}({{name}})
├ 支出 {{sol_ui_amount}} SOL
└ <a href="https://solscan.io/tx/{{signature}}">查看交易</a>
"""
)

_BUY_FAILED_TEMPLATE = env.from_string(
    """❌ 购买失败 ${{symbol}}({{name}})
{%- if signature %}
└ <a href="https://solscan.io/tx/{{signature}}">查看交易</a>
{%- endif %}
"""
)

_SELL_SUCCESS_TEMPLATE = env.from_string(
    """✅ 卖出成功
├ 卖出 {{token_ui_amount}} ${{symbol}}({{name}})
├ 收到 {{sol_ui_amount}} SOL
└ <a href="https://solscan.io/tx/{{signature}}">查看交易</a>
"""
)

_SELL_FAILED_TEMPLATE = env.from_string(
    """❌ 卖出失败 ${{symbol}}({{name}})
{%- if signature %}
└ <a href="https://solscan.io/tx/{{signature}}">查看交易</a>
{%- endif %}
"""
)


class SwapResultNotify:
    """用户交易结果通知"""

    def __init__(
        self,
        redis: aioredis.Redis,
        bot: Bot,
        batch_size: int = 10,
        poll_timeout_ms: int = 5000,
    ) -> None:
        self.redis = redis
        self.bot = bot
        self.consumer = SwapResultConsumer(
            redis_client=redis,
            consumer_group="swap_result_notify",
            consumer_name="swap_result_notify",
            batch_size=batch_size,
            poll_timeout_ms=poll_timeout_ms,
        )
        self.user_service = UserService()
        self.token_info_cache = TokenInfoCache()
        # Register the callback
        self.consumer.register_callback(self._handle_event)

    async def _build_message_for_copytrade(self, data: SwapResult) -> str:
        """构建用于跟单交易结果的消息"""
        event = data.swap_event
        assert isinstance(event.swap_direction, SwapDirection)

    async def _build_message_by_user_swap(self, data: SwapResult) -> str:
        """构建用于用户主动交易结果的消息"""
        event = data.swap_event
        swap_record = data.swap_record

        if event.swap_direction == SwapDirection.Buy:
            mint = event.output_mint
            token_info = await self.token_info_cache.get(mint)
            if token_info is None:
                raise ValueError(f"No token info found for {mint}")
            symbol = token_info.symbol
            name = token_info.token_name

            if swap_record is None:
                return _BUY_FAILED_TEMPLATE.render(symbol=symbol, name=name)
            elif swap_record.status != TransactionStatus.SUCCESS:
                return _BUY_FAILED_TEMPLATE.render(
                    symbol=symbol, name=name, signature=swap_record.signature
                )
            else:
                sol_ui_amount = swap_record.input_ui_amount
                token_ui_amount = swap_record.output_ui_amount
                return _BUY_SUCCESS_TEMPLATE.render(
                    symbol=symbol,
                    sol_ui_amount=sol_ui_amount,
                    token_ui_amount=token_ui_amount,
                    mint=mint,
                    name=name,
                    signature=data.transaction_hash,
                )
        elif event.swap_direction == SwapDirection.Sell:
            mint = event.input_mint
            token_info = await self.token_info_cache.get(mint)
            if token_info is None:
                raise ValueError(f"No token info found for {mint}")
            symbol = token_info.symbol
            name = token_info.token_name

            if swap_record is None:
                return _SELL_FAILED_TEMPLATE.render(symbol=symbol, name=name)
            elif swap_record.status != TransactionStatus.SUCCESS:
                return _SELL_FAILED_TEMPLATE.render(
                    symbol=symbol, name=name, signature=swap_record.signature
                )
            else:
                token_ui_amount = swap_record.input_ui_amount
                sol_ui_amount = swap_record.output_ui_amount
                return _SELL_SUCCESS_TEMPLATE.render(
                    symbol=symbol,
                    token_ui_amount=token_ui_amount,
                    sol_ui_amount=sol_ui_amount,
                    mint=mint,
                    name=name,
                    signature=data.transaction_hash,
                )

    async def build_message(self, data: SwapResult) -> str:
        """构建消息"""
        if data.by == "copytrade":
            return await self._build_message_for_copytrade(data)
        elif data.by == "user":
            return await self._build_message_by_user_swap(data)
        else:
            raise ValueError(f"Invalid by: {data.by}")

    async def _handle_event(self, data: SwapResult) -> None:
        try:
            logger.info(f"Handling SwapResult: {data}")
            message = await self.build_message(data)
            chat_id_list = await self.user_service.get_chat_id_by_pubkey(
                data.user_pubkey
            )

            async def _f(chat_id: int):
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode=ParseMode.HTML,
                    link_preview_options=LinkPreviewOptions(
                        is_disabled=True,
                    ),
                )

            tasks = []
            for chat_id in chat_id_list:
                tasks.append(asyncio.create_task(_f(chat_id)))
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(f"Failed to handle event: {e}")

    async def start(self):
        """启动用户交易结果通知"""
        logger.info("Starting swap result notify")
        self._consumer_task = asyncio.create_task(self.consumer.start())

    def stop(self):
        """停止用户交易结果通知"""
        if hasattr(self, "_consumer_task"):
            self.consumer.stop()

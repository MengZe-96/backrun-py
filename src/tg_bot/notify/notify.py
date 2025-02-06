import aioredis
from aiogram import Bot

from .smart_swap import SmartWalletSwapAlertNotify
from .swap_result import SwapResultNotify


class Notify:
    def __init__(self, redis: aioredis.Redis, bot: Bot):
        self.smart_wallet_swap_notify = SmartWalletSwapAlertNotify(redis, bot)
        self.swap_result_notify = SwapResultNotify(redis, bot)

    async def start(self):
        await self.smart_wallet_swap_notify.start()
        await self.swap_result_notify.start()

    async def stop(self):
        self.smart_wallet_swap_notify.stop()
        self.swap_result_notify.stop()

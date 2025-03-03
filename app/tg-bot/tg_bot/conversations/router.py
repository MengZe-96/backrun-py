from aiogram import Router

from tg_bot.conversations.asset import router as asset_router
from tg_bot.conversations.copytrade import router as copytrade_router
from tg_bot.conversations.home import router as home_router
from tg_bot.conversations.monitor import router as monitor_router
from tg_bot.conversations.setting import router as setting_router
from tg_bot.conversations.swap import router as swap_router
from tg_bot.conversations.wallet import router as wallet_router
from tg_bot.conversations.holding import router as holding_router

router = Router()

router.include_router(home_router)
router.include_router(copytrade_router)
router.include_router(swap_router)
router.include_router(monitor_router)
router.include_router(setting_router)
router.include_router(wallet_router)
router.include_router(asset_router)
router.include_router(holding_router)

from aiogram import Router

from .detail import router as detail_router
from .menu import router as menu_router

router = Router()
router.include_router(detail_router)
router.include_router(menu_router)
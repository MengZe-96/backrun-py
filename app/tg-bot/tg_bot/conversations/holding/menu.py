import re
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger

from tg_bot.conversations.holding.render import render
from tg_bot.conversations.states import HoldingStates

router = Router()


@router.callback_query(F.data == "holding")
async def start_holding(callback: CallbackQuery, state: FSMContext):
    """Handle holding menu button click"""
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    data = await render(callback=callback, page=1)
    await callback.message.edit_text(**data)
    await state.set_state(HoldingStates.MENU)

HOLDING_PAGE_PATTERN = re.compile(r"holding_page_(\d+)")
@router.callback_query(lambda c: HOLDING_PAGE_PATTERN.match(c.data))
async def holding_page(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    # Extract the holding page from callback data
    match = HOLDING_PAGE_PATTERN.match(callback.data)
    if not match:
        logger.warning("Invalid callback data for holding selection")
        return

    page = int(match.group(1))

    data = await render(callback=callback, page=page)
    await callback.message.edit_text(**data)
    await state.set_state(HoldingStates.MENU)


@router.callback_query(F.data == "back_to_home")
async def back_to_home(callback: CallbackQuery):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    from tg_bot.conversations.home.render import render

    data = await render(callback)
    await callback.message.edit_text(**data)
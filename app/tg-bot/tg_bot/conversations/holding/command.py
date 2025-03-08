from aiogram import Router
from aiogram.types import Message
from loguru import logger

from services.copytrade import CopyTradeService
from tg_bot.keyboards.holding import holding_menu_keyboard
from tg_bot.templates import render_holding_menu_message

router = Router()

# 收到/holding时触发该函数
async def holding(message: Message):
    """Handle holding menu button click"""
    if message.from_user is None:
        logger.warning("No message found in update")
        return
    # 2. 获取所有target的所有mint仓位，
    # message: 收入总计sol/支出总计sol, 当前仓位/最大仓位, 历史token数量, 页码
    # keyboard : target名称、当前仓位/最大仓位、当前仓位价值、当前token数量
    copytrade_states = await CopyTradeService.get_copytrade_states()
    sol_sold = 0
    sol_earned = 0
    current_position = 0
    max_position = 0
    token_number = 0
    
    for state in copytrade_states:
        sol_sold += state.sol_sold
        sol_earned += state.sol_earned
        current_position += state.current_position
        max_position += state.max_position
        token_number += state.token_number

    text = render_holding_menu_message(
        ui_sol_sold = sol_sold / 10 ** 9,
        ui_sol_earned = sol_earned / 10 ** 9,
        ui_current_position = current_position / 10 ** 9,
        ui_max_position = max_position / 10 ** 9,
        token_number = token_number,
        page=1,
        total_pages=len(copytrade_states) // 10 + 1,
    )

    keyboard = holding_menu_keyboard(copytrade_states, page=1)
    await message.answer(text, reply_markup=keyboard)

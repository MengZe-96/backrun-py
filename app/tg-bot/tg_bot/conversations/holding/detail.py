import re

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from solbot_common.log import logger
from solbot_common.utils import get_token_prices
from solbot_services.copytrade import CopyTradeService
from solbot_services.holding import HoldingService

from tg_bot.conversations.states import HoldingStates
from tg_bot.keyboards.holding import holding_detail_keyboard
from tg_bot.templates import render_holding_detail_message, render_holding_detail_summary_message
from tg_bot.utils import short_text

router = Router()

# Regular expression to match holding_detail_{target_wallet}_{page} pattern
HOLDING_DETAIL_PATTERN = re.compile(r"holding_detail_(\w+)_(\d+)")
@router.callback_query(lambda c: HOLDING_DETAIL_PATTERN.match(c.data))
async def handle_holding_selection(callback: CallbackQuery, state: FSMContext):
    """Handle selection of a specific target holding item"""
    if callback.message is None:
        return

    if not isinstance(callback.message, Message):
        return

    if callback.data is None:
        logger.warning("No data found in callback")
        return

    # Extract the target wallet from callback data
    match = HOLDING_DETAIL_PATTERN.match(callback.data)
    if not match:
        logger.warning("Invalid callback data for target holding selection")
        return

    target_wallet = str(match.group(1))
    page = int(match.group(2))

    # Fetch the holding data
    # 1. 获取单个target的所有mint仓位，用于在跟单战绩中第二层详情界面显示。token名称、token地址、my amount、target token amount、仓位价值、买入次数/最大次数、支出sol/收入sol、失败次数、过滤次数
    # 已过滤余额为0的holding，无仓位target。
    holdings = await HoldingService.get_positions(target_wallets=[target_wallet], mode = 1)
    logger.info(holdings)
    holding_message = "\n"
    ui_current_value = 0
    close_info = []
    if len(holdings) > 0:
        token_prices = await get_token_prices([holding.mint for holding in holdings])
        for idx, holding in enumerate(holdings):
            ui_current_value += holding.ui_my_amount * token_prices[holding.mint]
            close_info.append((holding.cp_pk, holding.mint)) # 清仓信息：顺序与idx一致，第一位为cp_pk, 第二位为mint，防止64bytes exceed error
            holding_message += render_holding_detail_message(
                idx = idx,
                token_symbol = holding.symbol,
                mint = holding.mint,
                ui_my_amount = holding.ui_my_amount,
                ui_target_amount = holding.ui_target_amount,
                ui_current_value = holding.ui_my_amount * token_prices[holding.mint],
                buy_time = holding.buy_time,
                max_buy_time = holding.max_buy_time,
                ui_sol_sold = holding.ui_sol_sold,
                ui_sol_earned = holding.ui_sol_earned,
            )

    copytrade_state = await CopyTradeService.get_target_setting(target_wallet=target_wallet)
    summary_message = render_holding_detail_summary_message(
        target_alias=short_text(copytrade_state.target_alias, max_length=10),
        target_wallet=target_wallet,
        holding_token_number = copytrade_state.token_number,
        ui_sol_sold = copytrade_state.sol_sold / 10 ** 9,
        ui_sol_earned = copytrade_state.sol_earned / 10 ** 9,
        ui_current_position = copytrade_state.current_position / 10 ** 9,
        ui_max_position = copytrade_state.max_position / 10 ** 9,
        ui_current_value= ui_current_value,
        failed_time = copytrade_state.failed_time,
        filtered_time = copytrade_state.filtered_time,
    )


    keyboard = holding_detail_keyboard(close_info, page=page)
    await callback.message.edit_text(text=summary_message+holding_message, reply_markup=keyboard)
    await state.set_state(HoldingStates.DETAIL)

    # 检查交易过期秒数。
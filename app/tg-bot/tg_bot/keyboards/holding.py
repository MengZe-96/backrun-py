from typing import List

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from solbot_common.models.tg_bot.copytrade import CopyTrade as CopyTradeModel

from tg_bot.utils import short_text


def holding_menu_keyboard(
    copytrade_states: List[CopyTradeModel] | None = None, page: int = 1
) -> InlineKeyboardMarkup:
    keyboard_items = []
    # 分页处理
    items_per_page = 10
    total_pages = len(copytrade_states) // items_per_page + 1
    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    # keyboard : target名称、当前仓位/最大仓位、当前token数量
    for copytrade_state in copytrade_states[start_idx:end_idx]:
        # PREF: 确认是否需要直接跳过未激活的跟单

        # PREF: 考虑部分target无holding，通过setting获取
        # copytrade_setting = await CopyTradeService.get_target_setting(swap_event.tx_event.who)
        indicator = ""
        if copytrade_state.current_position/ copytrade_state.max_position > 0.7:
            indicator = "🔴" # 仓位预警
        elif copytrade_state.current_position/ copytrade_state.max_position > 0.4:
            indicator = "🟡" # 仓位适中
        else:
            indicator = "🟢" # 仓位充裕

        keyboard_items.append(
            [
                InlineKeyboardButton(
                    text=f"{indicator} {short_text(copytrade_state.target_alias, max_length=5)}  💎 仓位 {copytrade_state.current_position/10**9:.2f}/{copytrade_state.max_position/10**9:.2f}SOL  🪙 币种 {copytrade_state.token_number}",
                    callback_data=f"holding_detail_{copytrade_state.target_wallet}_{page}",
                )
            ]
        )

    buttoms = []
    if page > 1:
        buttoms.append(InlineKeyboardButton(text="👈 上一页", callback_data=f"holding_page_{page-1}"))
    buttoms.append(InlineKeyboardButton(text="🔃 刷新", callback_data=f"holding_page_{page}"))
    if page < total_pages:
        buttoms.append(InlineKeyboardButton(text="👉 下一页", callback_data=f"holding_page_{page+1}"))


    return InlineKeyboardMarkup(
        inline_keyboard=[
            *keyboard_items,
            buttoms,
            [InlineKeyboardButton(text="⬅️ 返回", callback_data="back_to_home")]
        ]
    )

def holding_detail_keyboard(close_info: list, page: int) -> InlineKeyboardMarkup:
    """
    Detail keyboard for specific target holding.
    
    Generates an inline keyboard with buttons for each close position in close_info,
    arranged with up to three buttons per row, each labeled with an emoji and index.
    Includes a "Back" button at the end.
    
    :param close_info: List of close position indices or identifiers.
    :param page: Current page number for the back button callback.
    :return: InlineKeyboardMarkup object.
    """
    # PREF: 修复exceed 64 bytes error
    # 1. 采用copytrade中pk作为target_wallet替代
    # 2. 采用简写匹配
    buttons = []
    for idx, info in enumerate(close_info):
        button = InlineKeyboardButton(
            text=f"❎ 清仓 {idx}", # 按钮标签：emoji + idx
            callback_data=f"close_{info[0]}_{info[1]}"  # 回调数据，标明cp_pk、mint
        )
        buttons.append(button)

    # 添加返回按钮
    back_button = InlineKeyboardButton(
        text="⬅️ 返回",
        callback_data=f"holding_page_{page}"
    )
    buttons.append(back_button)
    # 将按钮按每行最多三个排列
    keyboard = [buttons[i:i+3] for i in range(0, len(buttons), 3)]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
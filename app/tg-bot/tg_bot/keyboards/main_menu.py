from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text="👛 我的钱包", callback_data="wallet"),
            InlineKeyboardButton(text="🎖️ 仓位统计", callback_data="holding"),
        ],
        [
            InlineKeyboardButton(text="🔮 所有持仓", callback_data="asset"),
            InlineKeyboardButton(text="📍 跟单地址", callback_data="copytrade"),
        ],
        [
            InlineKeyboardButton(text="🔔 交易监听", callback_data="monitor"),
            InlineKeyboardButton(text="⚙️ 其他设置", callback_data="set"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    return reply_markup

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from solbot_common.types.copytrade import CopyTrade, CopyTradeSummary

from tg_bot.utils import short_text


def copytrade_keyboard_menu(
    copytrade_items: list[CopyTradeSummary] | None = None,
) -> InlineKeyboardMarkup:
    if copytrade_items is None:
        copytrade_items = []

    items = []
    for idx, item in enumerate(copytrade_items):
        alias = item.target_alias
        if alias is not None:
            show_name = short_text(alias, max_length=10)
        else:
            show_name = short_text(item.target_wallet, max_length=10)

        items.append(
            [
                InlineKeyboardButton(
                    text="{} {}-{}".format(
                        "🟢" if item.active else "🔴", idx, show_name
                    ),
                    callback_data=f"copytrade_{item.pk}",
                )
            ]
        )

    if len(items) != 0:
        items.append(
            [
                InlineKeyboardButton(text="停止全部跟单", callback_data="stop_all_copytrade"),
            ]
        )

    buttoms = [
        InlineKeyboardButton(text="➕ 创建跟单", callback_data="create_copytrade"),
        InlineKeyboardButton(text="🔄 刷新", callback_data="refresh_copytrade"),
        InlineKeyboardButton(text="⬅️ 返回", callback_data="back_to_home"),
    ]

    return InlineKeyboardMarkup(
        inline_keyboard=[
            *items,
            buttoms,
        ]
    )


def create_copytrade_keyboard(udata: CopyTrade) -> InlineKeyboardMarkup:
    """Create keyboard for copytrade settings"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=(
                        "请输入钱包别名"
                        if udata.target_alias is None
                        else f"👨 名称：{short_text(udata.target_alias, 10)}"
                    ),
                    callback_data="set_target_alias",
                ),
                InlineKeyboardButton(
                    text=(
                        "请输入跟单地址"
                        if udata.target_wallet is None
                        else f"📍 地址：{short_text(str(udata.target_wallet), 10)}"
                    ),
                    callback_data="set_address",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="{} 自动跟买".format(
                        "✅" if udata.auto_buy else "🚫",
                    ),
                    callback_data="toggle_auto_buy",
                )
            ],
            [
                InlineKeyboardButton(
                    text="过滤阈值: {}SOL".format(
                        round(udata.filter_min_buy/10**9, 2),
                    ),
                    callback_data="set_filter_min_buy",
                ),
                InlineKeyboardButton(
                    text="仓位比例: {}%".format(
                        int(udata.auto_buy_ratio * 100),
                    ),
                    callback_data="set_auto_buy_ratio",
                ),
                InlineKeyboardButton(
                    text="最大仓位: {}SOL".format(
                        round(udata.max_position/10**9, 2),
                    ),
                    callback_data="set_max_position",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="最小加仓: {}SOL".format(
                        round(udata.min_buy_sol/10**9, 2),
                    ),
                    callback_data="set_min_buy_sol",
                ),
                InlineKeyboardButton(
                    text="最大加仓: {}SOL".format(
                        round(udata.max_buy_sol/10**9, 2),
                    ),
                    callback_data="set_max_buy_sol",
                ),
                InlineKeyboardButton(
                    text="最多买入: {}次".format(
                        udata.max_buy_time,
                    ),
                    callback_data="set_max_buy_time",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="{} 自动跟卖".format(
                        "✅" if udata.auto_sell else "🚫",
                    ),
                    callback_data="toggle_auto_sell",
                )
            ],
            [
                InlineKeyboardButton(
                    text="最小减仓: {}%".format(
                        int(udata.min_sell_ratio * 100),
                    ),
                    callback_data="set_min_sell_ratio",
                )
            ],
            [
                InlineKeyboardButton(
                    text="{} 防割模式".format(
                        "✅" if udata.anti_fast_trade else "🚫",
                    ),
                    callback_data="toggle_anti_fast_trade",
                )
            ],
            [
                InlineKeyboardButton(
                    text="识别阈值: {}秒".format(
                        udata.fast_trade_threshold,
                    ),
                    callback_data="set_fast_trade_threshold",
                ),
                InlineKeyboardButton(
                    text="累计间隔: {}秒".format(
                        udata.fast_trade_duration,
                    ),
                    callback_data="set_fast_trade_duration",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="休眠阈值: {}次".format(
                        udata.fast_trade_sleep_threshold,
                    ),
                    callback_data="set_fast_trade_sleep_threshold",
                ),
                InlineKeyboardButton(
                    text="休眠时长: {}秒".format(
                        udata.fast_trade_sleep_time,
                    ),
                    callback_data="set_fast_trade_sleep_time",
                )
            ],
            [
                InlineKeyboardButton(
                    text="{} 防夹模式".format(
                        "✅" if udata.anti_sandwich else "🚫",
                    ),
                    callback_data="toggle_anti_sandwich",
                ),
                InlineKeyboardButton(
                    text="优先费: {}SOL".format(
                        round(udata.priority/10**9,5),
                    ),
                    callback_data="set_priority",
                )
            ],
            [
                InlineKeyboardButton(
                    text="{} 自动滑点".format(
                        "✅" if udata.auto_slippage else "🚫",
                    ),
                    callback_data="toggle_auto_slippage",
                ),
                InlineKeyboardButton(
                    text="{} 自定义滑点: {}%".format(
                        "✅" if udata.auto_slippage is False else "",
                        int(udata.custom_slippage * 100),
                    ),
                    callback_data="set_custom_slippage",
                ),
            ],
            [
                InlineKeyboardButton(text="⬅️ 取消", callback_data="back_to_copytrade"),
                InlineKeyboardButton(text="✅ 确认创建", callback_data="submit_copytrade"),
            ],
        ],
    )


def edit_copytrade_keyboard(udata: CopyTrade) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=(
                        "请输入钱包别名"
                        if udata.target_alias is None
                        else f"👨 名称：{short_text(udata.target_alias, 10)}"
                    ),
                    callback_data="set_target_alias",
                ),
                InlineKeyboardButton(
                    text=(
                        "请输入跟单地址"
                        if udata.target_wallet is None
                        else f"📍 地址：{short_text(str(udata.target_wallet), 10)}"
                    ),
                    callback_data="null",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="{} 自动跟买".format(
                        "✅" if udata.auto_buy else "🚫",
                    ),
                    callback_data="toggle_auto_buy",
                )
            ],
            [
                InlineKeyboardButton(
                    text="过滤阈值: {}SOL".format(
                        round(udata.filter_min_buy/10**9, 2),
                    ),
                    callback_data="set_filter_min_buy",
                ),
                InlineKeyboardButton(
                    text="仓位比例: {}%".format(
                        int(udata.auto_buy_ratio * 100),
                    ),
                    callback_data="set_auto_buy_ratio",
                ),
                InlineKeyboardButton(
                    text="最大仓位: {}SOL".format(
                        round(udata.max_position/10**9, 2),
                    ),
                    callback_data="set_max_position",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="最小加仓: {}SOL".format(
                        round(udata.min_buy_sol/10**9, 2),
                    ),
                    callback_data="set_min_buy_sol",
                ),
                InlineKeyboardButton(
                    text="最大加仓: {}SOL".format(
                        round(udata.max_buy_sol/10**9, 2),
                    ),
                    callback_data="set_max_buy_sol",
                ),
                InlineKeyboardButton(
                    text="最多买入: {}次".format(
                        udata.max_buy_time,
                    ),
                    callback_data="set_max_buy_time",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="{} 自动跟卖".format(
                        "✅" if udata.auto_sell else "🚫",
                    ),
                    callback_data="toggle_auto_sell",
                )
            ],
            [
                InlineKeyboardButton(
                    text="最小减仓: {}%".format(
                        int(udata.min_sell_ratio * 100),
                    ),
                    callback_data="set_min_sell_ratio",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="{} 防割模式".format(
                        "✅" if udata.anti_fast_trade else "🚫",
                    ),
                    callback_data="toggle_anti_fast_trade",
                )
            ],
            [
                InlineKeyboardButton(
                    text="识别阈值: {}秒".format(
                        udata.fast_trade_threshold,
                    ),
                    callback_data="set_fast_trade_threshold",
                ),
                InlineKeyboardButton(
                    text="累计间隔: {}秒".format(
                        udata.fast_trade_duration,
                    ),
                    callback_data="set_fast_trade_duration",
                )
            ],
            [
                InlineKeyboardButton(
                    text="休眠阈值: {}次".format(
                        udata.fast_trade_sleep_threshold,
                    ),
                    callback_data="set_fast_trade_sleep_threshold",
                ),
                InlineKeyboardButton(
                    text="休眠时长: {}秒".format(
                        udata.fast_trade_sleep_time,
                    ),
                    callback_data="set_fast_trade_sleep_time",
                )
            ],
            [
                InlineKeyboardButton(
                    text="{} 防夹模式".format(
                        "✅" if udata.anti_sandwich else "🚫",
                    ),
                    callback_data="toggle_anti_sandwich",
                ),
                InlineKeyboardButton(
                    text="优先费: {}SOL".format(
                        round(udata.priority/10**9,5),
                    ),
                    callback_data="set_priority",
                )
            ],
            [
                InlineKeyboardButton(
                    text="{} 自动滑点".format(
                        "✅" if udata.auto_slippage else "🚫",
                    ),
                    callback_data="toggle_auto_slippage",
                ),
                InlineKeyboardButton(
                    text="{} 自定义滑点: {}%".format(
                        "✅" if udata.auto_slippage is False else "",
                        int(udata.custom_slippage*100),
                    ),
                    callback_data="set_custom_slippage",
                )
            ],
            [
                InlineKeyboardButton(text="删除跟单", callback_data="delete_copytrade"),
                InlineKeyboardButton(
                    text="停止跟单" if udata.active is True else "启动跟单",
                    callback_data="toggle_copytrade",
                ),
                InlineKeyboardButton(text="⬅️ 返回", callback_data="back_to_copytrade"),
            ],
        ],
    )


def take_profile_and_stop_loss_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="设置止盈止损", callback_data="set_tp_sl"),
            ],
            [
                InlineKeyboardButton(text="移动止盈止损", callback_data="move_tp_sl"),
            ],
            [
                InlineKeyboardButton(text="⬅️ 返回", callback_data="back_to_copytrade"),
                InlineKeyboardButton(text="✅ 确认", callback_data="submit_copytrade"),
            ],
        ],
    )

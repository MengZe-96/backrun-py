"""
Message templates for Telegram bot responses using Jinja2
"""

from typing import TYPE_CHECKING

from jinja2 import BaseLoader, Environment
from solbot_common.models.token_info import TokenInfo
from solbot_common.types.bot_setting import BotSetting as Setting
from solbot_common.types.holding import HoldingToken
from solbot_common.utils.utils import keypair_to_private_key
from solders.keypair import Keypair  # type: ignore

from tg_bot.models.monitor import Monitor
from tg_bot.utils.bot import get_bot_name

if TYPE_CHECKING:
    from tg_bot.notify.smart_swap import SwapMessage

# 创建 Jinja2 环境
env = Environment(loader=BaseLoader())

# 定义模板
HOLDING_MENU_TEMPLATE = env.from_string(
    """🎖️ 跟单战绩 🎖️
💰 收支：{{ui_sol_earned}}/{{ui_sol_sold}} SOL
💎 仓位：{{ui_current_position}}/{{ui_max_position}} SOL
🪙 累计币种：{{token_number}} TOKEN
📋 页码：{{page}}/{{total_pages}}
"""
)
def render_holding_menu_message(
        ui_sol_sold, 
        ui_sol_earned, 
        ui_current_position, 
        ui_max_position, 
        token_number,
        page,
        total_pages):
    return HOLDING_MENU_TEMPLATE.render(
        ui_sol_sold=round(ui_sol_sold, 2),
        ui_sol_earned=round(ui_sol_earned, 2),
        ui_current_position=round(ui_current_position, 2),
        ui_max_position=round(ui_max_position, 2),
        token_number=token_number,
        page = page,
        total_pages = total_pages
    )

HOLDING_DETAIL_SUMMARY_TEMPLATE = env.from_string(
    """🪴 聪明钱 {{target_alias}} 详情 🪴
    
📌 地址：<code>{{target_wallet}}</code>
💰 收支：{{ui_sol_earned}}/{{ui_sol_sold}} SOL
💎 仓位：{{ui_current_position}}/{{ui_max_position}} SOL
💵 价值：{{ui_current_value}} SOL
🪙 持仓：{{holding_token_number}} TOKENS
⌛️ 过滤：{{filtered_time}} TIMES
⛔ 失败：{{failed_time}} TIMES
"""
)
def render_holding_detail_summary_message(
        target_alias, 
        target_wallet, 
        ui_sol_sold, 
        ui_sol_earned, 
        ui_current_position, 
        ui_max_position, 
        ui_current_value,
        holding_token_number, 
        failed_time, 
        filtered_time
    ):
    return HOLDING_DETAIL_SUMMARY_TEMPLATE.render(
        target_alias = target_alias,
        target_wallet = target_wallet,
        ui_sol_sold = round(ui_sol_sold, 2),
        ui_sol_earned = round(ui_sol_earned, 2),
        ui_current_position = round(ui_current_position, 2),
        ui_max_position = round(ui_max_position, 2),
        ui_current_value = round(ui_current_value, 2),
        holding_token_number = holding_token_number,
        failed_time = failed_time,
        filtered_time = filtered_time
    )

HOLDING_DETAIL_TEMPLATE = env.from_string(
    """
——————🪙 {{idx}}: {{token_symbol}} 🪙——————
📍 地址：<code>{{mint}}</code>
💰 收支：{{ui_sol_earned}}/{{ui_sol_sold}} SOL
💎 仓位：{{ui_my_amount}}/{{ui_target_amount}} {{token_symbol}}
💵 价值：{{ui_current_value}} SOL
🛒 购买：{{buy_time}}/{{max_buy_time}} TIMES
"""
)
def render_holding_detail_message(
        idx,
        token_symbol,
        mint,
        ui_my_amount,
        ui_target_amount,
        ui_current_value,
        buy_time,
        max_buy_time,
        ui_sol_sold, 
        ui_sol_earned,
    ):
    return HOLDING_DETAIL_TEMPLATE.render(
        idx = idx,
        token_symbol = token_symbol,
        mint = mint,
        ui_my_amount = round(ui_my_amount, 2),
        ui_target_amount = round(ui_target_amount, 2),
        ui_current_value = round(ui_current_value, 2),
        buy_time = buy_time,
        max_buy_time = max_buy_time,
        ui_sol_sold = round(ui_sol_sold, 2), 
        ui_sol_earned = round(ui_sol_earned, 2),
    )

START_TEMPLATE = env.from_string(
    """🤖 Solana Copytrade Bot 🤖

💳 钱包地址:
<code>{{ wallet_address }}</code>

💰 钱包余额: {{ balance }} SOL
"""
)
# 移除无用信息，移除欢迎语、到期时间
# Hi {{ mention }}! 👋
# {%- if expiration_datetime %}
# ⌚ 到期时间: {{ expiration_datetime }}
# {%- endif %}

# 首次使用模板（未注册）
FIRST_USE_TEMPLATE = env.from_string(
    """👋 Solana Copytrade Bot 👋

💳 钱包地址:
<code>{{ wallet_address }}</code>

✅ Tips: 初始化bot完成，已生成一个新钱包。
可在任何时候使用 /wallet 命令更改钱包地址或导出私钥。
"""
)
# 移除无用信息，欢迎语和到期时间
# Hi {{ mention }}! 👋
# {%- if expiration_datetime %}
# ⌚ 到期时间: {{ expiration_datetime }}
# {%- endif %}

COPYTRADE_TEMPLATE = env.from_string(
    """复制交易设置:
目标钱包: <code>{{ target_wallet }}</code>
复制比例: {{ copy_ratio }}%
最大金额: {{ max_amount }} SOL
"""
)

COPYTRADE_MENU_TEMPLATE = env.from_string("""当前有 {{ total }} 个跟单，{{ active_cnt }} 个活跃""")

CREATE_COPYTRADE_MESSAGE = "📝 创建跟单"
EDIT_COPYTRADE_MESSAGE = "📝 编辑跟单"

# MONITOR
MONITOR_MENU_MESSAGE = """🔔 监听设置\n
监听您感兴趣的钱包，并实时接收他的交易通知
"""

MONITOR_MENU_TEMPLATE = env.from_string(
    """🔔 监听设置
监听您感兴趣的钱包，并实时接收他的交易通知

{% if monitors %}当前监听列表:
{%- for monitor in monitors[:10] %}
{{ loop.index }}. {% if monitor.active %}🟢{% else %}🔴{% endif %} <code>{{ monitor.target_wallet }}</code>{% if monitor.wallet_alias %} - {{ monitor.wallet_alias }}{% endif %}
{%- endfor %}
{% endif %}"""
)

CREATE_MONITOR_MESSAGE = "📝 创建监听"
EDIT_MONITOR_MESSAGE = env.from_string(
    """📝 编辑监听

目标钱包: <code>{{ monitor.target_wallet }}</code>
钱包别名: {{ monitor.wallet_alias }}
状态: {% if monitor.active %}🟢监听中{% else %}🔴已暂停{% endif %}
"""
)


def render_monitor_menu(monitors: list[Monitor]):
    """渲染监听菜单消息"""
    return MONITOR_MENU_TEMPLATE.render(monitors=monitors)


def render_edit_monitor_message(monitor: Monitor):
    return EDIT_MONITOR_MESSAGE.render(monitor=monitor)


# NOTIFY
NOTIFY_SWAP_TEMPLATE = env.from_string(
    """🔔 交易通知\n
{{ human_description }}

📛 钱包别名: {{ wallet_alias }} <code>{{ who }}</code>(点击复制)
📝 类型: {{ tx_type_cn }}
💱 交易方向: {{ tx_direction }}
🪙 代币名称: ${{ token_symbol }} ({{ token_name }})
🪙 代币地址: <code>{{ mint }}</code>
💰 交易数量: {{ "%.4f"|format(from_amount) }} → {{ "%.4f"|format(to_amount) }}
📊 持仓变化: {{ position_change_formatted }}
💎 当前持仓: {{ "%.4f"|format(post_amount) }}
⏰ 时间: {{ tx_time }}
🔗 交易详情: <a href="https://solscan.io/tx/{{ signature }}">Solscan</a>
📊 K线盯盘: <a href="https://gmgn.ai/sol/token/{{ mint }}">GMGN</a> | <a href="https://dexscreener.com/solana/{{ mint }}">DexScreen</a>
"""
)


def render_first_use_message(mention, wallet_address, expiration_datetime):
    return FIRST_USE_TEMPLATE.render(
        mention=mention,
        wallet_address=wallet_address,
        expiration_datetime=expiration_datetime,
    )


def render_start_message(mention, wallet_address, balance, expiration_datetime):
    """渲染开始消息"""
    return START_TEMPLATE.render(
        mention=mention,
        wallet_address=wallet_address,
        balance=balance,
        expiration_datetime=expiration_datetime,
    )


def render_copytrade_message(target_wallet, copy_ratio, max_amount):
    """渲染复制交易消息"""
    return COPYTRADE_TEMPLATE.render(
        target_wallet=target_wallet,
        copy_ratio=copy_ratio,
        max_amount=max_amount,
    )


def render_copytrade_menu(total, active_cnt):
    """渲染复制交易菜单消息"""
    return COPYTRADE_MENU_TEMPLATE.render(total=total, active_cnt=active_cnt)


def render_notify_swap(
    swap_message: "SwapMessage",
):
    """渲染交易通知消息"""
    return NOTIFY_SWAP_TEMPLATE.render(
        human_description=swap_message.human_description,
        token_name=swap_message.token_name,
        token_symbol=swap_message.token_symbol,
        wallet_alias=swap_message.wallet_alias,
        tx_type_cn=swap_message.tx_type_cn,
        from_amount=swap_message.from_amount,
        to_amount=swap_message.to_amount,
        position_change_formatted=swap_message.position_change_formatted,
        post_amount=swap_message.post_amount,
        tx_time=swap_message.tx_time,
        signature=swap_message.signature,
        who=swap_message.target_wallet,
        mint=swap_message.mint,
        tx_direction=swap_message.tx_direction,
    )


SETTING_TEMPLATE = env.from_string(
    """钱包地址:
<code>{{ wallet_address }}</code> (点击复制)

🚀️ 快速滑点: {{ quick_slippage }}
🛡️ 防夹滑点: {{ sandwich_slippage }}%
🟢 买入优先费:  {{ buy_priority_fee }} SOL
🔴 卖出优先费:  {{ sell_priority_fee }} SOL

自动滑点: 根据K线自动调整滑点，范围2.5%~30%。
开启后，仅对快速模式生效，防夹模式不生效。
"""
)


def render_setting_message(setting: Setting):
    wallet_address = setting.wallet_address
    sandwich_slippage = setting.get_sandwich_slippage_pct()
    buy_priority_fee = setting.buy_priority_fee
    sell_priority_fee = setting.sell_priority_fee
    if setting.auto_slippage:
        quick_slippage = "自动"
    else:
        quick_slippage = f"{setting.get_quick_slippage_pct()}%"

    return SETTING_TEMPLATE.render(
        wallet_address=wallet_address,
        quick_slippage=quick_slippage,
        sandwich_slippage=sandwich_slippage,
        buy_priority_fee=buy_priority_fee,
        sell_priority_fee=sell_priority_fee,
    )


SWAP_TOKEN_TEMPLATE = env.from_string(
    """{{ symbol }}({{ name }})
<code>{{ mint }}</code>
(长按复制)

价格 ${{ price }}
📊 K线盯盘: <a href="https://gmgn.ai/sol/token/{{ mint }}">GMGN</a> | <a href="https://dexscreener.com/solana/{{ mint }}">DexScreen</a>

💎 持仓 {{ holding_sol_balance }} SOL
| 代币 {{ holding_token_balance }}

⚙️ 买 {{ buy_priority_fee }} SOL | 卖 {{ sell_priority_fee }} SOL (点击 /set 修改)
"""
)


def render_swap_token_message(token_info: TokenInfo, setting: Setting):
    return SWAP_TOKEN_TEMPLATE.render(
        symbol=token_info.symbol,
        name=token_info.token_name,
        mint=token_info.mint,
        buy_priority_fee=setting.buy_priority_fee,
        sell_priority_fee=setting.sell_priority_fee,
    )


# 🔔 安全: Mint弃权 ✅ / 黑名单 ✅ / 烧池子 100%✅
# ✅ 前10持仓大户: 15.35%
# 🐀 老鼠仓: --
# ✅ 池子: $1.4M (2,804.72 SOL)
# 💊 Pump外盘(29D)
# 🐦 推特 | 🌏 官网 | ✈️ 电报

# 价格 $0.04779    市值 $47.8M    K线盯盘

# 💎 持仓 1.041 SOL ($228.625)
# | 代币 4,784.11 EVAN
# | 起飞 3.41% 🚀
# | 平均成本 $0.04621 (市值: $46.2M)
# | 总买入 1 SOL
# | 总卖出 0 SOL
# 💳 余额 0.72515 SOL

# ---------------------
# ⛽ 建议优先费Tip: 快速 0.0029 SOL | 极速 0.0038 SOL

BUY_SELL_TEMPLATE = env.from_string(
    """💡交易命令介绍:

/buy: 立即买入代币
/sell: 立即卖出代币
/create: 创建买/卖限价单

示例命令：
/buy ukHH6c7mMyiWCf1b9pnWe25TSpkDDt3H5pQZgZ74J82 0.5
表示立即买入 0.5 SOL BOME代币

/sell ukHH6c7mMyiWCf1b9pnWe25TSpkDDt3H5pQZgZ74J82 50
/sell ukHH6c7mMyiWCf1b9pnWe25TSpkDDt3H5pQZgZ74J82 50%
表示立即卖出 50% BOME代币持仓
    """
)

WALLET_TEMPLATE = env.from_string(
    """🔑 钱包地址:
<code>{{ wallet }}</code> (点击复制)

钱包余额: {{ sol_balance }} SOL <a href="https://gmgn.ai/sol/address/{{ wallet }}">交易记录</a>
WSOL余额: {{ wsol_balance }} WSOL
"""
)


def render_wallet_message(wallet: str, sol_balance: float, wsol_balance: float):
    return WALLET_TEMPLATE.render(
        wallet=wallet,
        sol_balance=sol_balance,
        wsol_balance=wsol_balance,
    )


NEW_WALLET_TEMPLATE = env.from_string(
    """🆕 更换新钱包
更换新钱包
⚠️ 暂时仅支持1个钱包，更换新钱包私钥后，服务器会删除老钱包私钥，无法找回！
⚠️ 更换钱包私钥后，原地址的所有挂单、钱包跟单、CTO跟单、策略等均会自动关闭！请手动处理资产
⚠️ 请立即备份老钱包私钥 (不要分享给其他人)
备份私钥：
<code>{{ private_key }}</code> (点击复制)

Tips: 本消息将在 30 秒后自动删除
"""
)


def render_new_wallet_message(keypair: Keypair):
    private_key = keypair_to_private_key(keypair)
    return NEW_WALLET_TEMPLATE.render(private_key=private_key)


EXPORT_WALLET_TEMPLATE = env.from_string(
    """🔑 钱包地址:
<code>{{ wallet }}</code> (点击复制)

🔐 钱包私钥:
<code>{{ private_key }}</code> (点击复制)

⚠️ 请不要分享私钥给任何人 (本条消息5秒后销毁)
"""
)


def render_export_wallet_message(keypair: Keypair):
    pubkey = keypair.pubkey().__str__()
    private_key = keypair_to_private_key(keypair)

    return EXPORT_WALLET_TEMPLATE.render(
        wallet=pubkey,
        private_key=private_key,
    )


ASSET_TEMPLATE = env.from_string(
    """🔑 钱包地址:
<code>{{ wallet }}</code> (点击复制)

💰 钱包余额: {{ sol_balance }} SOL

🔮 代币 | 数量 | 价值（SOL）
{%- for token in tokens %}
{{ loop.index }}. <a href="https://t.me/{{ bot_name }}?start=asset_{{ token.mint }}">{{ token.symbol }}</a> | {{ token.balance_str }} | {{values[token.mint]}} SOL
{%- endfor -%}
"""
)


def render_asset_message(wallet: str, sol_balance: float, tokens: list[HoldingToken], prices: dict):
    bot_name = get_bot_name()
    values = {}
    for token in tokens:
        values[token.mint] = str(round(prices[token.mint] * token.balance, 4))
    return ASSET_TEMPLATE.render(
        bot_name=bot_name,
        wallet=wallet,
        sol_balance=sol_balance,
        tokens=tokens,
        values=values
    )

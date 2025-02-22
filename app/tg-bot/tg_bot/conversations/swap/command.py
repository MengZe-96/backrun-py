import time

from aiogram.types import Message

from cache import TokenInfoCache
from common.constants import SOL_DECIMAL, WSOL
from common.cp.swap_event import SwapEventProducer
from common.log import logger
from common.types.swap import SwapEvent
from common.types.enums import SwapDirection
from common.utils import calculate_auto_slippage
from db.redis import RedisClient
from services.bot_setting import BotSettingService as SettingService
from tg_bot.services.user import UserService
from tg_bot.templates import BUY_SELL_TEMPLATE


from tg_bot.utils.solana import validate_solana_address
from .render import render

setting_service = SettingService()
user_service = UserService()
token_info_cache = TokenInfoCache()


async def info_command(message: Message):
    """发送 Token Addres，回复代币交易界面"""
    logger.debug(message)
    if message.from_user is None:
        logger.warning("No message found in update")
        return

    if message.text is None:
        logger.warning("No text found in message")
        return

    text = message.text.strip()
    valid = validate_solana_address(text)
    if not valid:
        await message.answer(
            text="❌ 无效的 Token Address，请重新输入：",
        )
        return

    token_info = await token_info_cache.get(text)
    if token_info is None:
        logger.info(f"❌ 未找到 {text} 代币信息")
        return

    chat_id = message.from_user.id
    wallet = await user_service.get_pubkey(chat_id)
    setting = await setting_service.get(chat_id, wallet)

    await message.answer(
        **render(
            token_info=token_info,
            setting=setting,
        ),
    )


async def swap_command(message: Message):
    if message.from_user is None:
        logger.warning("No message found in update")
        return

    if message.text is None:
        logger.warning("No text found in message")
        return

    text = message.text.strip()
    if text == "/buy" or text == "/sell":
        await message.answer(
            text=BUY_SELL_TEMPLATE.render(),
        )
        return

    try:
        cmd, token_mint, ui_amount = text.split()
    except ValueError:
        await message.answer(
            text="❌ 输入格式错误，请重新输入：",
        )
        return

    cmd = cmd.replace("/", "")

    if cmd not in ["buy", "sell"]:
        await message.answer(
            text="❌ 输入格式错误，请重新输入：",
        )
        return

    chat_id = message.from_user.id
    wallet = await user_service.get_pubkey(chat_id)
    setting = await setting_service.get(chat_id, wallet)
    if setting is None:
        raise ValueError("Setting not found")

    token_info = await token_info_cache.get(token_mint)
    if token_info is None:
        logger.info(f"No token info found for {token_mint}")
        await message.answer("❌ 无法查询到该代币信息")
        return

    if cmd == "buy":
        input_mint = WSOL.__str__()
        output_mint = token_info.mint
        from_amount = int(float(ui_amount) * 10 ** SOL_DECIMAL)
        swap_direction = SwapDirection.Buy
    else:
        if ui_amount.endswith("%"):
            await message.answer(
                text="暂时不支持以百分比卖出",
            )
            return
        from_amount = int(float(ui_amount) * 10 ** token_info.decimals)
        input_mint = token_info.mint
        output_mint = WSOL.__str__()
        swap_direction = SwapDirection.Sell

    if setting.sandwich_mode:
        slippage_bps = setting.sandwich_slippage_bps
    elif setting.auto_slippage:
        slippage_bps = await calculate_auto_slippage(
            input_mint=input_mint,
            output_mint=output_mint,
            amount=from_amount,
            # TODO: add swap_mode
            # swap_mode="ExactIn" if cmd == "buy" else "ExactOut"
            swap_mode="ExactIn",
            min_slippage_bps=setting.min_slippage,
            max_slippage_bps=setting.max_slippage,
        )
    else:
        slippage_bps = setting.quick_slippage

    swap_event_producer = SwapEventProducer(RedisClient.get_instance())

    swap_event = SwapEvent(
        user_pubkey=wallet,
        swap_direction=swap_direction,
        input_mint=input_mint,
        output_mint=output_mint,
        amount=from_amount,
        ui_amount=from_amount,
        slippage_bps=slippage_bps,
        timestamp=int(time.time()),
        priority_fee=(
            setting.buy_priority_fee if cmd == "buy" else setting.sell_priority_fee
        ),
    )
    if setting.auto_slippage:
        swap_event.dynamic_slippage = True
        swap_event.min_slippage_bps = setting.min_slippage
        swap_event.max_slippage_bps = setting.max_slippage

    await swap_event_producer.produce(swap_event=swap_event)

    if cmd == "buy":
        await message.answer(
            f"🚀 {token_info.symbol} 买 {ui_amount} SOL, 滑点：{slippage_bps / 100}%"
        )
        logger.info(
            f"Buy {ui_amount} SOL for {token_info.symbol}, slippage: {slippage_bps / 100} %"
        )
    else:
        await message.answer(
            f"🚀 卖 {ui_amount} {token_info.symbol}, 滑点：{slippage_bps / 100}%"
        )
        logger.info(
            f"Sell {ui_amount} {token_info.symbol} for  SOL, slippage: {slippage_bps / 100} %"
        )

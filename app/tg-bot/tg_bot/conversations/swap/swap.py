import re
import time
from typing import cast

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ForceReply, Message
from loguru import logger
from solbot_cache import TokenInfoCache
from solbot_common.constants import SOL_DECIMAL, WSOL
from solbot_common.cp.swap_event import SwapEventProducer
from solbot_common.types.bot_setting import BotSetting as Setting
from solbot_common.types.swap import SwapEvent
from solbot_common.types.tx import TxEvent, TxType
from solbot_common.types.enums import SwapDirection
from solbot_common.utils import calculate_auto_slippage
from solbot_db.redis import RedisClient
from solbot_services.bot_setting import BotSettingService as SettingService
from solbot_services.holding import HoldingService
from solbot_services.copytrade import CopyTradeService

from tg_bot.conversations.setting.menu import setting_menu
from tg_bot.conversations.states import SwapStates
from tg_bot.services.user import UserService
from tg_bot.utils import get_setting_from_db
from tg_bot.utils.message import invalid_input_and_request_reinput
from tg_bot.utils.swap import get_token_account_balance

from .render import render

router = Router()
setting_service = SettingService()
user_service = UserService()
token_info_cache = TokenInfoCache()


TOKEN_MINT_PATTERN = re.compile(r"\.*[^(]+\([^)]+\)\n([1-9A-HJ-NP-Za-km-z]{43,44})")


def extract_token_mint_from_swap_menu(text: str) -> str | None:
    """Extract token mint from swap menu text

    Args:
        text (str): Swap menu text

    Returns:
        str | None: Token mint

    """
    match = TOKEN_MINT_PATTERN.search(text)
    if match:
        return match.group(1)
    return None


@router.callback_query(F.data == "swap")
async def start_swap(callback: CallbackQuery, state: FSMContext):
    """Handle swap menu button click"""
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    await callback.message.answer(
        "输入代币合约地址，开始买卖👇🏻",
        reply_markup=ForceReply(),
    )

    await state.set_state(SwapStates.WAITING_FOR_TOKEN_MINT)


@router.message(SwapStates.WAITING_FOR_TOKEN_MINT)
async def show_token_menu(message: Message, state: FSMContext):
    if message.text is None:
        logger.warning("No text found in message")
        return

    token_mint = message.text.strip()

    # TODO: validate token mint

    if message.from_user is None:
        raise ValueError("User not found")

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

    await state.update_data(setting=setting, token_info=token_info, wallet=wallet)
    data = render(token_info=token_info, setting=setting)
    await message.answer(**data)


REFRESH_PATTERN = re.compile(r"swap:refresh_(\w+)")


@router.callback_query(lambda c: REFRESH_PATTERN.match(c.data))
async def refresh_token_menu(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        return

    if callback.data is None:
        logger.warning("No data found in callback")
        return

    match = REFRESH_PATTERN.match(callback.data)
    if not match:
        logger.warning("Invalid callback data for copytrade selection")
        return

    token_mint = match.group(1)
    chat_id = callback.from_user.id
    wallet = await user_service.get_pubkey(chat_id)
    setting = await setting_service.get(chat_id, wallet)
    if setting is None:
        raise ValueError("Setting not found")

    token_info = await token_info_cache.get(token_mint)
    if token_info is None:
        logger.info(f"No token info found for {token_mint}")
        await callback.message.answer("❌ 无法查询到该代币信息")
        return

    await state.update_data(setting=setting, token_info=token_info, wallet=wallet)
    data = render(token_info=token_info, setting=setting)
    await callback.message.edit_text(**data)


@router.callback_query(F.data == "toggle_quick_mode")
async def toggle_quick_mode(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    if callback.message.from_user is None:
        return

    chat_id = callback.message.chat.id
    wallet = await user_service.get_pubkey(chat_id)
    setting = await setting_service.get(chat_id=chat_id, wallet_address=wallet)
    if setting is None:
        raise ValueError("Setting not found")

    setting.auto_slippage = not setting.auto_slippage
    if setting.auto_slippage:
        setting.sandwich_mode = False

    data = await state.get_data()
    text = callback.message.text
    if text is None:
        raise ValueError("Text not found in message")

    token_mint = extract_token_mint_from_swap_menu(text)
    if token_mint is None:
        raise ValueError("Token mint not found in message text")

    token_info = await token_info_cache.get(token_mint)
    if token_info is None:
        raise ValueError("Token info not found in state")

    await setting_service.set(setting)
    await state.update_data(setting=setting, token_info=token_info)
    data = render(token_info=token_info, setting=setting)
    await callback.message.edit_text(**data)


@router.callback_query(F.data == "toggle_sandwich_mode")
async def toggle_sandwich_mode(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    chat_id = callback.message.chat.id
    wallet = await user_service.get_pubkey(chat_id)
    setting = await setting_service.get(chat_id=chat_id, wallet_address=wallet)
    if setting is None:
        raise ValueError("Setting not found")

    setting.sandwich_mode = not setting.sandwich_mode
    if setting.sandwich_mode:
        setting.auto_slippage = False

    data = await state.get_data()
    text = callback.message.text
    if text is None:
        raise ValueError("Text not found in message")

    token_mint = extract_token_mint_from_swap_menu(text)
    if token_mint is None:
        raise ValueError("Token mint not found in message text")

    token_info = await token_info_cache.get(token_mint)
    if token_info is None:
        raise ValueError("Token info not found in state")

    await setting_service.set(setting)
    await state.update_data(setting=setting, token_info=token_info)
    data = render(token_info=token_info, setting=setting)
    await callback.message.edit_text(**data)


@router.callback_query(F.data == "set")
async def _setting_menu(callback: CallbackQuery, state: FSMContext):
    await setting_menu(callback, state, replace=False)


BUY_PATTERN = re.compile(r"buy_(\d*\.?\d+)_(\w+)")


@router.callback_query(lambda c: BUY_PATTERN.match(c.data))
async def buy(callback: CallbackQuery, state: FSMContext):
    """Handle buy button click"""
    if callback.message is None:
        return

    if not isinstance(callback.message, Message):
        return

    if callback.data is None:
        logger.warning("No data found in callback")
        return

    match = BUY_PATTERN.match(callback.data)
    if not match:
        logger.warning("Invalid callback data for copytrade selection")
        return

    from_amount = float(match.group(1))
    token_mint = match.group(2)
    data = await state.get_data()

    token_info = await token_info_cache.get(token_mint)
    if token_info is None:
        logger.info(f"No token info found for {token_mint}")
        await callback.answer("❌ 无法查询到该代币信息")
        return

    setting = cast(Setting, data.get("setting"))
    if setting is None:
        setting = await get_setting_from_db(callback.from_user.id)
    if setting is None:
        raise ValueError("Setting not found in state")

    wallet = cast(str, data.get("wallet"))
    if wallet is None:
        wallet = await user_service.get_pubkey(callback.from_user.id)
    if wallet is None:
        raise ValueError("Wallet not found in state")

    timestamp = int(time.time())
    if setting.sandwich_mode:
        slippage_bps = setting.sandwich_slippage_bps
        swap_event = SwapEvent(
            user_pubkey=wallet,
            swap_direction=SwapDirection.Buy,
            input_mint=WSOL.__str__(),
            output_mint=token_info.mint,
            amount=int(from_amount * 10 ** SOL_DECIMAL),
            ui_amount=from_amount,
            slippage_bps=slippage_bps,
            timestamp=timestamp,
            priority_fee=setting.buy_priority_fee,
        )
    elif setting.auto_slippage:
        # 需要计算出 slippage
        slippage_bps = await calculate_auto_slippage(
            input_mint=WSOL.__str__(),
            output_mint=token_info.mint,
            amount=int(from_amount * 10 ** SOL_DECIMAL),
            min_slippage_bps=setting.min_slippage,
            max_slippage_bps=setting.max_slippage,
        )
        swap_event = SwapEvent(
            user_pubkey=wallet,
            swap_direction=SwapDirection.Buy,
            input_mint=WSOL.__str__(),
            output_mint=token_info.mint,
            amount=int(from_amount * 10 ** SOL_DECIMAL),
            ui_amount=from_amount,
            timestamp=timestamp,
            slippage_bps=slippage_bps,
            dynamic_slippage=True,
            min_slippage_bps=setting.min_slippage,
            max_slippage_bps=setting.max_slippage,
            priority_fee=setting.buy_priority_fee,
        )
    else:
        slippage_bps = setting.quick_slippage
        swap_event = SwapEvent(
            user_pubkey=wallet,
            swap_direction=SwapDirection.Buy,
            input_mint=WSOL.__str__(),
            output_mint=token_info.mint,
            amount=int(from_amount * 10 ** SOL_DECIMAL),
            ui_amount=from_amount,
            slippage_bps=slippage_bps,
            timestamp=timestamp,
            priority_fee=setting.buy_priority_fee,
        )

    swap_event_producer = SwapEventProducer(RedisClient.get_instance())
    await swap_event_producer.produce(swap_event=swap_event)
    logger.debug(swap_event)

    await callback.message.answer(f"🚀 {token_info.symbol} 买 {from_amount} SOL")
    logger.info(f"Buy {from_amount} SOL for {token_info.symbol}, Wallet: {wallet}")


BUYX_PATTERN = re.compile(r"buyx_(\w+)")


@router.callback_query(lambda c: BUYX_PATTERN.match(c.data))
async def start_buyx(callback: CallbackQuery, state: FSMContext):
    """Handle buyx button click"""
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    if callback.data is None:
        logger.warning("No data found in callback")
        return

    match = BUYX_PATTERN.match(callback.data)
    if not match:
        logger.warning("Invalid callback data for copytrade selection")
        return

    token_mint = match.group(1)
    data = await state.get_data()

    token_info = await token_info_cache.get(token_mint)
    if token_info is None:
        logger.info(f"No token info found for {token_mint}")
        await callback.answer("❌ 无法查询到该代币信息")
        return

    setting = cast(Setting, data.get("setting"))
    if setting is None:
        setting = await get_setting_from_db(callback.from_user.id)
    if setting is None:
        raise ValueError("Setting not found in state")

    wallet = cast(str, data.get("wallet"))
    if wallet is None:
        wallet = await user_service.get_pubkey(callback.from_user.id)
    if wallet is None:
        raise ValueError("Wallet not found in state")

    # Store original message details for later updates
    await state.update_data(
        original_message_id=callback.message.message_id,
        original_chat_id=callback.message.chat.id,
        setting=setting,
        token_mint=token_mint,
        wallet=wallet,
    )

    # Send prompt message with force reply
    msg = await callback.message.answer(
        "👋 请输入买入金额（SOL）：",
        parse_mode="HTML",
        reply_markup=ForceReply(),
    )

    # Store prompt message details for cleanup
    await state.update_data(
        prompt_message_id=msg.message_id,
        prompt_chat_id=msg.chat.id,
    )

    await state.set_state(SwapStates.WAITING_BUY_AMOUNT)


@router.message(F.text, SwapStates.WAITING_BUY_AMOUNT)
async def handle_buyx(message: Message, state: FSMContext):
    if not message.text:
        return

    try:
        ui_amount = float(message.text.strip())
    except ValueError:
        await invalid_input_and_request_reinput(
            text="❌ 无效的买入金额，请重新输入：",
            last_message=message,
            state=state,
        )
        return

    if ui_amount <= 0:
        await invalid_input_and_request_reinput(
            text="❌ 买入金额必须大于 0，请重新输入：",
            last_message=message,
            state=state,
        )

    data = await state.get_data()
    setting: Setting | None = data.get("setting")
    if setting is None:
        if message.from_user is None:
            raise ValueError("Setting not found")
        setting = await get_setting_from_db(message.from_user.id)
        await state.update_data(setting=setting)
    if setting is None:
        raise ValueError("Setting not found")

    token_mint = cast(str, data.get("token_mint"))
    if token_mint is None:
        raise ValueError("Token mint not found in state")

    token_info = await token_info_cache.get(token_mint)
    if token_info is None:
        message.answer("❌ 等待自定义购买金额超时，请重新点击买入按钮")
        return

    wallet = cast(str, data.get("wallet"))
    if wallet is None:
        if message.from_user is None:
            raise ValueError("Wallet not found")
        wallet = await user_service.get_pubkey(message.from_user.id)
    if wallet is None:
        raise ValueError("Wallet not found in state")

    amount = int(ui_amount * 10 ** SOL_DECIMAL)
    timestamp = int(time.time())
    if setting.sandwich_mode:
        slippage_bps = setting.sandwich_slippage_bps
        swap_event = SwapEvent(
            user_pubkey=wallet,
            swap_direction=SwapDirection.Buy,
            input_mint=WSOL.__str__(),
            output_mint=token_info.mint,
            amount=amount,
            ui_amount=ui_amount,
            slippage_bps=slippage_bps,
            timestamp=timestamp,
            priority_fee=setting.buy_priority_fee,
        )
    elif setting.auto_slippage:
        # 需要计算出 slippage
        slippage_bps = await calculate_auto_slippage(
            input_mint=WSOL.__str__(),
            output_mint=token_info.mint,
            amount=int(ui_amount * 10 ** SOL_DECIMAL),
        )
        swap_event = SwapEvent(
            user_pubkey=wallet,
            swap_direction=SwapDirection.Buy,
            input_mint=WSOL.__str__(),
            output_mint=token_info.mint,
            amount=amount,
            ui_amount=ui_amount,
            timestamp=timestamp,
            slippage_bps=slippage_bps,
            dynamic_slippage=True,
            min_slippage_bps=setting.min_slippage,
            max_slippage_bps=setting.max_slippage,
            priority_fee=setting.buy_priority_fee,
        )
    else:
        slippage_bps = setting.quick_slippage
        swap_event = SwapEvent(
            user_pubkey=wallet,
            swap_direction=SwapDirection.Buy,
            input_mint=WSOL.__str__(),
            output_mint=token_info.mint,
            amount=amount,
            ui_amount=ui_amount,
            slippage_bps=slippage_bps,
            timestamp=timestamp,
            priority_fee=setting.buy_priority_fee,
        )

    swap_event_producer = SwapEventProducer(RedisClient.get_instance())
    await swap_event_producer.produce(swap_event=swap_event)
    logger.debug(swap_event)

    await message.answer(f"🚀 {token_info.symbol} 买 {ui_amount} SOL")
    logger.info(f"Buy {ui_amount} SOL for {token_info.symbol}, Wallet: {wallet}")

    await state.set_state()

# cp_pk, mint
CLOSE_PATTERN = re.compile(r"close_(\d+)_(\w+)")
@router.callback_query(lambda c: CLOSE_PATTERN.match(c.data))
async def close(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        return

    if not isinstance(callback.message, Message):
        return
    
    if callback.data is None:
        logger.warning("No data found in callback")
        return

    match = CLOSE_PATTERN.match(callback.data)
    if not match:
        logger.warning("Invalid callback data for colse operation")
        return

    cp_pk = int(match.group(1))
    token_mint = match.group(2)
    data = await state.get_data()
    target_wallet = await CopyTradeService.get_target_wallet_by_pk(cp_pk)
    holding = await HoldingService.get_positions(target_wallets=[target_wallet], mint=token_mint, mode=3)

    setting = cast(Setting, data.get("setting"))
    if setting is None:
        setting = await get_setting_from_db(callback.from_user.id)
    if setting is None:
        raise ValueError("Setting not found in state")

    wallet = cast(str, data.get("wallet"))
    if wallet is None:
        wallet = await user_service.get_pubkey(callback.from_user.id)
    if wallet is None:
        raise ValueError("Wallet not found in state")

    timestamp = int(time.time())

    # 增加tx_event伪造为copytrade，以便更新holding
    tx_event = TxEvent(
        signature = "user_close_target_position",
        from_amount = holding.target_amount,
        from_decimals = holding.decimals,
        to_amount = 0,
        to_decimals = 9,
        mint = holding.mint,
        who = target_wallet,
        tx_type = TxType.CLOSE_POSITION,
        tx_direction = SwapDirection.Sell,
        timestamp = timestamp,
        pre_token_amount = holding.target_amount,
        post_token_amount = 0,
        # program_id: str | None = None
    )

    if holding.my_amount <= 0:
        await callback.answer("❌ 卖出失败，您的余额不足")
        return

    timestamp = int(time.time())
    if setting.sandwich_mode:
        slippage_bps = setting.sandwich_slippage_bps
        swap_event = SwapEvent(
            tx_event = tx_event,
            by = 'copytrade',
            user_pubkey=wallet,
            swap_direction=SwapDirection.Sell,
            input_mint=holding.mint,
            output_mint=WSOL.__str__(),
            amount=holding.my_amount,
            ui_amount=holding.ui_my_amount,
            slippage_bps=slippage_bps,
            timestamp=timestamp,
            priority_fee=setting.sell_priority_fee,
        )
    elif setting.auto_slippage:
        # 需要计算出 slippage
        slippage_bps = await calculate_auto_slippage(
            input_mint=holding.mint,
            output_mint=WSOL.__str__(),
            amount=holding.my_amount,
            min_slippage_bps=setting.min_slippage,
            max_slippage_bps=setting.max_slippage,
        )
        swap_event = SwapEvent(
            tx_event = tx_event,
            by = 'copytrade',
            user_pubkey=wallet,
            swap_direction=SwapDirection.Sell,
            input_mint=holding.mint,
            output_mint=WSOL.__str__(),
            amount=holding.my_amount,
            ui_amount=holding.ui_my_amount,
            timestamp=timestamp,
            slippage_bps=slippage_bps,
            dynamic_slippage=True,
            min_slippage_bps=setting.min_slippage,
            max_slippage_bps=setting.max_slippage,
            priority_fee=setting.sell_priority_fee,
        )
    else:
        slippage_bps = setting.quick_slippage
        swap_event = SwapEvent(
            tx_event = tx_event,
            by = 'copytrade',
            user_pubkey=wallet,
            swap_direction=SwapDirection.Sell,
            input_mint=holding.mint,
            output_mint=WSOL.__str__(),
            amount=holding.my_amount,
            ui_amount=holding.ui_my_amount,
            slippage_bps=slippage_bps,
            timestamp=timestamp,
            priority_fee=setting.sell_priority_fee,
        )

    swap_event_producer = SwapEventProducer(RedisClient.get_instance())
    await swap_event_producer.produce(swap_event=swap_event)

    await callback.message.answer(f"🚀 卖出 {holding.ui_my_amount} 个 {holding.symbol}")
    logger.info(f"Sell {holding.ui_my_amount} {holding.symbol}, Wallet: {wallet}")


SELL_PATTERN = re.compile(r"sell_(\d*\.?\d+)_(\w+)")
@router.callback_query(lambda c: SELL_PATTERN.match(c.data))
async def sell(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        return

    if not isinstance(callback.message, Message):
        return

    if callback.data is None:
        logger.warning("No data found in callback")
        return

    match = SELL_PATTERN.match(callback.data)
    if not match:
        logger.warning("Invalid callback data for copytrade selection")
        return

    sell_pct = float(match.group(1))
    token_mint = match.group(2)
    data = await state.get_data()

    if not (0 < sell_pct <= 100):
        await callback.answer("❌ 请输入正确的比例，取值范围：0~100")
        return

    # 将百分比转换为小数
    sell_pct = sell_pct / 100

    token_info = await token_info_cache.get(token_mint)
    if token_info is None:
        logger.info(f"No token info found for {token_mint}")
        await callback.answer("❌ 无法查询到该代币信息")
        return

    setting = cast(Setting, data.get("setting"))
    if setting is None:
        setting = await get_setting_from_db(callback.from_user.id)
    if setting is None:
        raise ValueError("Setting not found in state")

    wallet = cast(str, data.get("wallet"))
    if wallet is None:
        wallet = await user_service.get_pubkey(callback.from_user.id)
    if wallet is None:
        raise ValueError("Wallet not found in state")

    result = await get_token_account_balance(token_mint=token_info.mint, owner=wallet)
    if result is None:
        await callback.answer("❌ 该账户没有持有该代币，无法卖出")
        return

    balance = result["amount"]
    decimals = result["decimals"]
    if sell_pct == 1:
        amount = balance
    else:
        amount = int(balance * sell_pct)
    ui_amount = amount / 10**decimals

    if amount <= 0:
        await callback.answer("❌ 卖出失败，您的余额不足")
        return

    timestamp = int(time.time())
    if setting.sandwich_mode:
        slippage_bps = setting.sandwich_slippage_bps
        swap_event = SwapEvent(
            user_pubkey=wallet,
            swap_direction=SwapDirection.Sell,
            input_mint=token_info.mint,
            output_mint=WSOL.__str__(),
            amount=amount,
            ui_amount=ui_amount,
            slippage_bps=slippage_bps,
            timestamp=timestamp,
            priority_fee=setting.sell_priority_fee,
        )
    elif setting.auto_slippage:
        # 需要计算出 slippage
        slippage_bps = await calculate_auto_slippage(
            input_mint=token_info.mint,
            output_mint=WSOL.__str__(),
            amount=int(ui_amount * 10 ** SOL_DECIMAL),
            min_slippage_bps=setting.min_slippage,
            max_slippage_bps=setting.max_slippage,
        )
        swap_event = SwapEvent(
            user_pubkey=wallet,
            swap_direction=SwapDirection.Sell,
            input_mint=token_info.mint,
            output_mint=WSOL.__str__(),
            amount=amount,
            ui_amount=ui_amount,
            timestamp=timestamp,
            slippage_bps=slippage_bps,
            dynamic_slippage=True,
            min_slippage_bps=setting.min_slippage,
            max_slippage_bps=setting.max_slippage,
            priority_fee=setting.sell_priority_fee,
        )
    else:
        slippage_bps = setting.quick_slippage
        swap_event = SwapEvent(
            user_pubkey=wallet,
            swap_direction=SwapDirection.Sell,
            input_mint=token_info.mint,
            output_mint=WSOL.__str__(),
            amount=amount,
            ui_amount=ui_amount,
            slippage_bps=slippage_bps,
            timestamp=timestamp,
            priority_fee=setting.sell_priority_fee,
        )

    swap_event_producer = SwapEventProducer(RedisClient.get_instance())
    await swap_event_producer.produce(swap_event=swap_event)

    await callback.message.answer(f"🚀 卖出 {ui_amount} 个 {token_info.symbol}")
    logger.info(f"Sell {ui_amount} {token_info.symbol}, Wallet: {wallet}")


CUSTOM_SELL_PATTERN = re.compile(r"sell_custom_(\w+)")


@router.callback_query(lambda c: CUSTOM_SELL_PATTERN.match(c.data))
async def start_sellx(callback: CallbackQuery, state: FSMContext):
    """Handle sellx button click"""
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    if callback.data is None:
        logger.warning("No data found in callback")
        return

    match = CUSTOM_SELL_PATTERN.match(callback.data)
    if not match:
        logger.warning("Invalid callback data")
        return

    token_mint = match.group(1)
    data = await state.get_data()

    token_info = await token_info_cache.get(token_mint)
    if token_info is None:
        logger.info(f"No token info found for {token_mint}")
        await callback.answer("❌ 无法查询到该代币信息")
        return

    setting = cast(Setting, data.get("setting"))
    if setting is None:
        setting = await get_setting_from_db(callback.from_user.id)
    if setting is None:
        raise ValueError("Setting not found in state")

    wallet = cast(str, data.get("wallet"))
    if wallet is None:
        wallet = await user_service.get_pubkey(callback.from_user.id)
    if wallet is None:
        raise ValueError("Wallet not found in state")

    # Store original message details for later updates
    await state.update_data(
        original_message_id=callback.message.message_id,
        original_chat_id=callback.message.chat.id,
        setting=setting,
        token_mint=token_mint,
        wallet=wallet,
    )

    # Send prompt message with force reply
    msg = await callback.message.answer(
        "👋 请输入卖出比例，例如：10（卖出 10% 的代币）",
        parse_mode="HTML",
        reply_markup=ForceReply(),
    )

    # Store prompt message details for cleanup
    await state.update_data(
        prompt_message_id=msg.message_id,
        prompt_chat_id=msg.chat.id,
    )

    await state.set_state(SwapStates.WAITING_SELL_PCT)


@router.message(F.text, SwapStates.WAITING_SELL_PCT)
async def handle_sellx(message: Message, state: FSMContext):
    if not message.text:
        return

    try:
        sell_pct = float(message.text.strip())
    except ValueError:
        await invalid_input_and_request_reinput(
            text="❌ 请输入数字：",
            last_message=message,
            state=state,
        )
        return

    if not (0 < sell_pct <= 100):
        await invalid_input_and_request_reinput(
            text="❌ 请输入正确的比例，取值范围：0~100",
            last_message=message,
            state=state,
        )
        return

    sell_pct = sell_pct / 100
    data = await state.get_data()
    token_mint = cast(str, data.get("token_mint"))
    token_info = await token_info_cache.get(token_mint)
    if token_info is None:
        logger.info(f"No token info found for {token_mint}")
        await message.answer("❌ 无法查询到该代币信息")
        return

    setting = cast(Setting, data.get("setting"))
    if setting is None:
        if message.from_user is None:
            raise ValueError("Setting not found")
        setting = await get_setting_from_db(message.from_user.id)
    if setting is None:
        raise ValueError("Setting not found in state")

    wallet = cast(str, data.get("wallet"))
    if wallet is None:
        if message.from_user is None:
            raise ValueError("Wallet not found")
        wallet = await user_service.get_pubkey(message.from_user.id)
    if wallet is None:
        raise ValueError("Wallet not found in state")

    result = await get_token_account_balance(token_mint=token_info.mint, owner=wallet)
    if result is None:
        await message.answer("❌ 该账户没有持有该代币，无法卖出")
        return

    balance = result["amount"]
    decimals = result["decimals"]
    if sell_pct == 1:
        amount = balance
    else:
        amount = int(balance * sell_pct)
    ui_amount = amount / 10**decimals

    if amount <= 0:
        await message.answer("❌ 卖出失败，您的余额不足")
        return

    timestamp = int(time.time())
    if setting.sandwich_mode:
        slippage_bps = setting.sandwich_slippage_bps
        swap_event = SwapEvent(
            user_pubkey=wallet,
            swap_direction=SwapDirection.Sell,
            input_mint=token_info.mint,
            output_mint=WSOL.__str__(),
            amount=amount,
            ui_amount=ui_amount,
            slippage_bps=slippage_bps,
            timestamp=timestamp,
            priority_fee=setting.sell_priority_fee,
        )
    elif setting.auto_slippage:
        # 需要计算出 slippage
        slippage_bps = await calculate_auto_slippage(
            input_mint=token_info.mint,
            output_mint=WSOL.__str__(),
            swap_direction=SwapDirection.Sell,
        )
        swap_event = SwapEvent(
            user_pubkey=wallet,
            swap_direction=SwapDirection.Sell,
            input_mint=token_info.mint,
            output_mint=WSOL.__str__(),
            amount=amount,
            ui_amount=ui_amount,
            timestamp=timestamp,
            slippage_bps=slippage_bps,
            dynamic_slippage=True,
            min_slippage_bps=setting.min_slippage,
            max_slippage_bps=setting.max_slippage,
            priority_fee=setting.sell_priority_fee,
        )
    else:
        slippage_bps = setting.quick_slippage
        swap_event = SwapEvent(
            user_pubkey=wallet,
            swap_direction=SwapDirection.Sell,
            input_mint=token_info.mint,
            output_mint=WSOL.__str__(),
            amount=amount,
            ui_amount=ui_amount,
            slippage_bps=slippage_bps,
            timestamp=timestamp,
            priority_fee=setting.sell_priority_fee,
        )

    swap_event_producer = SwapEventProducer(RedisClient.get_instance())
    await swap_event_producer.produce(swap_event=swap_event)

    await message.answer(f"🚀 卖出 {ui_amount} 个 {token_info.symbol}")
    logger.info(f"Sell {ui_amount} {token_info.symbol}, Wallet: {wallet}")

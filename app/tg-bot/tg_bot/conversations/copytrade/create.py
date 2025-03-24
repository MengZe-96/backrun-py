import asyncio
from typing import cast

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ForceReply, Message
from loguru import logger
from solbot_common.types.copytrade import CopyTrade
from solbot_services.bot_setting import BotSettingService as SettingService
from solbot_common.constants import SOL_DECIMAL

from tg_bot.conversations.copytrade.render import render
from tg_bot.conversations.states import CopyTradeStates
from tg_bot.keyboards.copytrade import create_copytrade_keyboard
from tg_bot.services.copytrade import CopyTradeService
from tg_bot.services.user import UserService
from tg_bot.templates import CREATE_COPYTRADE_MESSAGE
from tg_bot.utils import validate_solana_address

router = Router()
copy_trade_service = CopyTradeService()
setting_service = SettingService()
user_service = UserService()


@router.callback_query(F.data == "create_copytrade")
async def start_create_copytrade(callback: CallbackQuery, state: FSMContext):
    """Handle create copytrade button click"""
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    chat_id = callback.message.chat.id
    pubkey = await user_service.get_pubkey(chat_id=chat_id)

    # Initialize copytrade settings
    copytrade_settings = CopyTrade(
        owner=pubkey,
        chat_id=chat_id,
    )

    # Store settings in state
    await state.update_data(copytrade_settings=copytrade_settings)

    keyboard = create_copytrade_keyboard(copytrade_settings)

    await callback.message.edit_text(
        CREATE_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await state.set_state(CopyTradeStates.CREATING)


@router.callback_query(F.data == "set_address", CopyTradeStates.CREATING)
async def start_set_address(callback: CallbackQuery, state: FSMContext):
    """Handle set address button click"""
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    # Store original message details for later updates
    await state.update_data(
        original_message_id=callback.message.message_id,
        original_chat_id=callback.message.chat.id,
    )

    # Send prompt message with force reply
    msg = await callback.message.answer(
        "👋 请输入要跟单的目标钱包地址：",
        parse_mode="HTML",
        reply_markup=ForceReply(),
    )

    # Store prompt message details for cleanup
    await state.update_data(
        prompt_message_id=msg.message_id,
        prompt_chat_id=msg.chat.id,
    )

    await state.set_state(CopyTradeStates.CREATE_WAITING_FOR_ADDRESS)


@router.message(CopyTradeStates.CREATE_WAITING_FOR_ADDRESS)
async def handle_set_address(message: Message, state: FSMContext):
    """Handle wallet address input"""
    if not message.text:
        return

    address = message.text.strip()

    # Validate address
    if not validate_solana_address(address):
        msg = await message.answer(
            "❌ 无效的 Solana 钱包地址，请重新输入：", reply_markup=ForceReply()
        )
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=msg.chat.id,
                message_id=msg.message_id,
            )
        return

    # Get stored data
    data = await state.get_data()
    copytrade_settings: CopyTrade = data["copytrade_settings"]

    # Update settings
    copytrade_settings.target_wallet = address
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    # Clean up messages
    try:
        await message.delete()  # Delete user's input
        await message.bot.delete_message(  # Delete prompt message
            chat_id=data["prompt_chat_id"],
            message_id=data["prompt_message_id"],
        )
    except Exception as e:
        logger.warning(f"Failed to delete messages: {e}")

    # Update original message
    keyboard = create_copytrade_keyboard(copytrade_settings)

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=CREATE_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    await state.set_state(CopyTradeStates.CREATING)


@router.callback_query(F.data == "set_target_alias", CopyTradeStates.CREATING)
async def start_set_alias(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    # Store original message details for later updates
    await state.update_data(
        original_message_id=callback.message.message_id,
        original_chat_id=callback.message.chat.id,
    )

    # Send prompt message with force reply
    msg = await callback.message.answer(
        "👋 请输入钱包别名：",
        parse_mode="HTML",
        reply_markup=ForceReply(),
    )

    # Store prompt message details for cleanup
    await state.update_data(
        prompt_message_id=msg.message_id,
        prompt_chat_id=msg.chat.id,
    )

    await state.set_state(CopyTradeStates.CREATE_WAITING_FOR_ALIAS)


@router.message(CopyTradeStates.CREATE_WAITING_FOR_ALIAS)
async def handle_set_alias(message: Message, state: FSMContext):
    if not message.text:
        return

    alias = message.text.strip()

    # Get stored data
    data = await state.get_data()
    copytrade_settings: CopyTrade | None = cast(CopyTrade | None, data.get("copytrade_settings"))

    if copytrade_settings is None:
        logger.warning("Copytrade settings not found in state")
        return

    # Update settings
    copytrade_settings.target_alias = alias
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    # Clean up messages
    try:
        await message.delete()  # Delete user's input
        await message.bot.delete_message(  # Delete prompt message
            chat_id=data["prompt_chat_id"],
            message_id=data["prompt_message_id"],
        )
    except Exception as e:
        logger.warning(f"Failed to delete messages: {e}")

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=CREATE_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=create_copytrade_keyboard(copytrade_settings),
    )

    await state.set_state(CopyTradeStates.CREATING)


@router.callback_query(F.data == "set_filter_min_buy", CopyTradeStates.CREATING)
async def start_set_filter_min_buy(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    # Store original message details for later updates
    await state.update_data(
        original_message_id=callback.message.message_id,
        original_chat_id=callback.message.chat.id,
    )

    # Send prompt message with force reply
    msg = await callback.message.answer(
        "👋 请输入过滤最小的SOL数量（0-10）：",
        parse_mode="HTML",
        reply_markup=ForceReply(),
    )

    # Store prompt message details for cleanup
    await state.update_data(
        prompt_message_id=msg.message_id,
        prompt_chat_id=msg.chat.id,
    )

    await state.set_state(CopyTradeStates.CREATE_WAITING_FOR_FILTER_MIN_BUY)


@router.message(CopyTradeStates.CREATE_WAITING_FOR_FILTER_MIN_BUY)
async def handle_set_filter_min_buy(message: Message, state: FSMContext):
    if not message.text:
        return

    filter_min_buy = message.text.strip()

    # Get stored data
    data = await state.get_data()
    copytrade_settings: CopyTrade | None = cast(CopyTrade | None, data.get("copytrade_settings"))

    if copytrade_settings is None:
        logger.warning("Copytrade settings not found in state")
        return

    try:
        filter_min_buy = float(filter_min_buy)
    except ValueError:
        msg = await message.reply("❌ 无效的买入数量，请重新输入：", reply_markup=ForceReply())
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    if filter_min_buy < 0 or filter_min_buy > 10:
        msg = await message.reply("❌ 无效的买入数量，请重新输入：", reply_markup=ForceReply())
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    # Update settings
    copytrade_settings.filter_min_buy = int(filter_min_buy * 10 ** 9)
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    # Clean up messages
    try:
        await message.delete()  # Delete user's input
        await message.bot.delete_message(  # Delete prompt message
            chat_id=data["prompt_chat_id"],
            message_id=data["prompt_message_id"],
        )
    except Exception as e:
        logger.warning(f"Failed to delete messages: {e}")

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=CREATE_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=create_copytrade_keyboard(copytrade_settings),
    )

    await state.set_state(CopyTradeStates.CREATING)


@router.callback_query(F.data == "set_max_buy_time", CopyTradeStates.CREATING)
async def start_set_max_buy_time(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

        # Store original message details for later updates
    await state.update_data(
        original_message_id=callback.message.message_id,
        original_chat_id=callback.message.chat.id,
    )

    # Send prompt message with force reply
    msg = await callback.message.answer(
        "👋 请输入单token最大买入次数（1-1000）：",
        parse_mode="HTML",
        reply_markup=ForceReply(),
    )

    # Store prompt message details for cleanup
    await state.update_data(
        prompt_message_id=msg.message_id,
        prompt_chat_id=msg.chat.id,
    )

    await state.set_state(CopyTradeStates.CREATE_WAITING_FOR_MAX_BUY_TIME)


@router.message(CopyTradeStates.CREATE_WAITING_FOR_MAX_BUY_TIME)
async def handle_set_max_buy_time(message: Message, state: FSMContext):
    if not message.text:
        return

    max_buy_time = message.text.strip()

    # Get stored data
    data = await state.get_data()
    copytrade_settings: CopyTrade | None = cast(CopyTrade | None, data.get("copytrade_settings"))

    if copytrade_settings is None:
        logger.warning("Copytrade settings not found in state")
        return

    try:
        max_buy_time = int(max_buy_time)
    except ValueError:
        msg = await message.reply(
            "❌ 无效的买入次数，请重新输入：", reply_markup=ForceReply()
        )
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    if max_buy_time <= 0 or max_buy_time > 1000:
        msg = await message.reply(
            "❌ 无效的买入次数，请重新输入：", reply_markup=ForceReply()
        )
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    # Update settings
    copytrade_settings.max_buy_time = max_buy_time
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    # Clean up messages
    try:
        await message.delete()  # Delete user's input
        await message.bot.delete_message(  # Delete prompt message
            chat_id=data["prompt_chat_id"],
            message_id=data["prompt_message_id"],
        )
    except Exception as e:
        logger.warning(f"Failed to delete messages: {e}")

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=CREATE_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=create_copytrade_keyboard(copytrade_settings),
    )
    await state.set_state(CopyTradeStates.CREATING)


################# 睡眠时间
@router.callback_query(F.data == "set_fast_trade_sleep_time", CopyTradeStates.CREATING)
async def start_set_fast_trade_sleep_time(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    # Store original message details for later updates
    await state.update_data(
        original_message_id=callback.message.message_id,
        original_chat_id=callback.message.chat.id,
    )

    # Send prompt message with force reply
    msg = await callback.message.answer(
        "👋 请输入防割睡眠时长（1-100000）：",
        parse_mode="HTML",
        reply_markup=ForceReply(),
    )

    # Store prompt message details for cleanup
    await state.update_data(
        prompt_message_id=msg.message_id,
        prompt_chat_id=msg.chat.id,
    )

    await state.set_state(CopyTradeStates.CREATE_WAITING_FOR_FAST_TRADE_SLEEP_TIME)


@router.message(CopyTradeStates.CREATE_WAITING_FOR_FAST_TRADE_SLEEP_TIME)
async def handle_set_fast_trade_sleep_time(message: Message, state: FSMContext):
    if not message.text:
        return

    fast_trade_sleep_time = message.text.strip()

    # Get stored data
    data = await state.get_data()
    copytrade_settings: CopyTrade | None = cast(CopyTrade | None, data.get("copytrade_settings"))

    if copytrade_settings is None:
        logger.warning("Copytrade settings not found in state")
        return

    try:
        fast_trade_sleep_time = int(fast_trade_sleep_time)
    except ValueError:
        msg = await message.reply(
            "❌ 无效的睡眠时间，请重新输入：", reply_markup=ForceReply()
        )
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    if fast_trade_sleep_time < 1 or fast_trade_sleep_time > 100000:
        msg = await message.reply(
            "❌ 无效的睡眠时间，请重新输入：", reply_markup=ForceReply()
        )
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    # Update settings
    copytrade_settings.fast_trade_sleep_time = fast_trade_sleep_time
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    # Clean up messages
    try:
        await message.delete()  # Delete user's input
        await message.bot.delete_message(  # Delete prompt message
            chat_id=data["prompt_chat_id"],
            message_id=data["prompt_message_id"],
        )
    except Exception as e:
        logger.warning(f"Failed to delete messages: {e}")

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=CREATE_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=create_copytrade_keyboard(copytrade_settings),
    )
    await state.set_state(CopyTradeStates.CREATING)

@router.callback_query(F.data == "set_min_buy_sol", CopyTradeStates.CREATING)
async def start_set_min_buy_sol(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    # Store original message details for later updates
    await state.update_data(
        original_message_id=callback.message.message_id,
        original_chat_id=callback.message.chat.id,
    )

    # Send prompt message with force reply
    msg = await callback.message.answer(
        "👋 请输入最小加仓SOL数量（0-100）：",
        parse_mode="HTML",
        reply_markup=ForceReply(),
    )

    # Store prompt message details for cleanup
    await state.update_data(
        prompt_message_id=msg.message_id,
        prompt_chat_id=msg.chat.id,
    )

    await state.set_state(CopyTradeStates.CREATE_WAITING_FOR_MIN_BUY_SOL)


@router.message(CopyTradeStates.CREATE_WAITING_FOR_MIN_BUY_SOL)
async def handle_set_min_buy_sol(message: Message, state: FSMContext):
    if not message.text:
        return

    min_buy_sol = message.text.strip()

    # Get stored data
    data = await state.get_data()
    copytrade_settings: CopyTrade | None = cast(
        CopyTrade | None, data.get("copytrade_settings")
    )

    if copytrade_settings is None:
        logger.warning("Copytrade settings not found in state")
        return

    try:
        min_buy_sol = float(min_buy_sol)
    except ValueError:
        msg = await message.reply(
            "❌ 无效的买入数量，请重新输入：", reply_markup=ForceReply()
        )
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    if min_buy_sol < 0 or min_buy_sol > 100:
        msg = await message.reply(
            "❌ 无效的买入数量，请重新输入：", reply_markup=ForceReply()
        )
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    # Update settings
    copytrade_settings.min_buy_sol = int(min_buy_sol * 10 ** 9)
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    # Clean up messages
    try:
        await message.delete()  # Delete user's input
        await message.bot.delete_message(  # Delete prompt message
            chat_id=data["prompt_chat_id"],
            message_id=data["prompt_message_id"],
        )
    except Exception as e:
        logger.warning(f"Failed to delete messages: {e}")

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=CREATE_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=create_copytrade_keyboard(copytrade_settings),
    )

    await state.set_state(CopyTradeStates.CREATING)

@router.callback_query(F.data == "set_max_buy_sol", CopyTradeStates.CREATING)
async def start_set_max_buy_sol(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    # Store original message details for later updates
    await state.update_data(
        original_message_id=callback.message.message_id,
        original_chat_id=callback.message.chat.id,
    )

    # Send prompt message with force reply
    msg = await callback.message.answer(
        "👋 请输入最大加仓SOL数量（0.01-100）：",
        parse_mode="HTML",
        reply_markup=ForceReply(),
    )

    # Store prompt message details for cleanup
    await state.update_data(
        prompt_message_id=msg.message_id,
        prompt_chat_id=msg.chat.id,
    )

    await state.set_state(CopyTradeStates.CREATE_WAITING_FOR_MAX_BUY_SOL)


@router.message(CopyTradeStates.CREATE_WAITING_FOR_MAX_BUY_SOL)
async def handle_set_max_buy_sol(message: Message, state: FSMContext):
    if not message.text:
        return

    max_buy_sol = message.text.strip()

    # Get stored data
    data = await state.get_data()
    copytrade_settings: CopyTrade | None = cast(
        CopyTrade | None, data.get("copytrade_settings")
    )

    if copytrade_settings is None:
        logger.warning("Copytrade settings not found in state")
        return

    try:
        max_buy_sol = float(max_buy_sol)
    except ValueError:
        msg = await message.reply(
            "❌ 无效的买入数量，请重新输入：", reply_markup=ForceReply()
        )
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    if max_buy_sol < 0.01 or max_buy_sol > 100:
        msg = await message.reply(
            "❌ 无效的买入数量，请重新输入：", reply_markup=ForceReply()
        )
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    # Update settings
    copytrade_settings.max_buy_sol = int(max_buy_sol * 10 ** 9)
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    # Clean up messages
    try:
        await message.delete()  # Delete user's input
        await message.bot.delete_message(  # Delete prompt message
            chat_id=data["prompt_chat_id"],
            message_id=data["prompt_message_id"],
        )
    except Exception as e:
        logger.warning(f"Failed to delete messages: {e}")

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=CREATE_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=create_copytrade_keyboard(copytrade_settings),
    )

    await state.set_state(CopyTradeStates.CREATING)

@router.callback_query(F.data == "set_min_sell_ratio", CopyTradeStates.CREATING)
async def start_set_min_sell_ratio(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    # Store original message details for later updates
    await state.update_data(
        original_message_id=callback.message.message_id,
        original_chat_id=callback.message.chat.id,
    )

    # Send prompt message with force reply
    msg = await callback.message.answer(
        "👋 请输入最小卖出比例（0.01-1）：",
        parse_mode="HTML",
        reply_markup=ForceReply(),
    )

    # Store prompt message details for cleanup
    await state.update_data(
        prompt_message_id=msg.message_id,
        prompt_chat_id=msg.chat.id,
    )

    await state.set_state(CopyTradeStates.CREATE_WAITING_FOR_MIN_SELL_RATIO)


@router.message(CopyTradeStates.CREATE_WAITING_FOR_MIN_SELL_RATIO)
async def handle_set_min_sell_ratio(message: Message, state: FSMContext):
    if not message.text:
        return

    min_sell_ratio = message.text.strip()

    # Get stored data
    data = await state.get_data()
    copytrade_settings: CopyTrade | None = cast(
        CopyTrade | None, data.get("copytrade_settings")
    )

    if copytrade_settings is None:
        logger.warning("Copytrade settings not found in state")
        return

    try:
        min_sell_ratio = float(min_sell_ratio)
    except ValueError:
        msg = await message.reply(
            "❌ 无效的卖出比例，请重新输入：", reply_markup=ForceReply()
        )
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    if min_sell_ratio <= 0.01 or min_sell_ratio > 1:
        msg = await message.reply(
            "❌ 无效的卖出比例，请重新输入：", reply_markup=ForceReply()
        )
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    # Update settings
    copytrade_settings.min_sell_ratio = min_sell_ratio
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    # Clean up messages
    try:
        await message.delete()  # Delete user's input
        await message.bot.delete_message(  # Delete prompt message
            chat_id=data["prompt_chat_id"],
            message_id=data["prompt_message_id"],
        )
    except Exception as e:
        logger.warning(f"Failed to delete messages: {e}")

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=CREATE_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=create_copytrade_keyboard(copytrade_settings),
    )

    await state.set_state(CopyTradeStates.CREATING)

@router.callback_query(F.data == "set_fast_trade_threshold", CopyTradeStates.CREATING)
async def start_set_fast_trade_threshold(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    # Store original message details for later updates
    await state.update_data(
        original_message_id=callback.message.message_id,
        original_chat_id=callback.message.chat.id,
    )

    # Send prompt message with force reply
    msg = await callback.message.answer(
        "👋 请输入快速交易的时间阈值（1-10000秒）：",
        parse_mode="HTML",
        reply_markup=ForceReply(),
    )

    # Store prompt message details for cleanup
    await state.update_data(
        prompt_message_id=msg.message_id,
        prompt_chat_id=msg.chat.id,
    )

    await state.set_state(CopyTradeStates.CREATE_WAITING_FOR_FAST_TRADE_THRESHOLD)


@router.message(CopyTradeStates.CREATE_WAITING_FOR_FAST_TRADE_THRESHOLD)
async def handle_set_fast_trade_threshold(message: Message, state: FSMContext):
    if not message.text:
        return

    fast_trade_threshold = message.text.strip()

    # Get stored data
    data = await state.get_data()
    copytrade_settings: CopyTrade | None = cast(
        CopyTrade | None, data.get("copytrade_settings")
    )

    if copytrade_settings is None:
        logger.warning("Copytrade settings not found in state")
        return

    try:
        fast_trade_threshold = int(fast_trade_threshold)
    except ValueError:
        msg = await message.reply(
            "❌ 无效的时间阈值，请重新输入：", reply_markup=ForceReply()
        )
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    if fast_trade_threshold < 1 or fast_trade_threshold > 10000:
        msg = await message.reply(
            "❌ 无效的时间阈值，请重新输入：", reply_markup=ForceReply()
        )
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    # Update settings
    copytrade_settings.fast_trade_threshold = fast_trade_threshold
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    # Clean up messages
    try:
        await message.delete()  # Delete user's input
        await message.bot.delete_message(  # Delete prompt message
            chat_id=data["prompt_chat_id"],
            message_id=data["prompt_message_id"],
        )
    except Exception as e:
        logger.warning(f"Failed to delete messages: {e}")

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=CREATE_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=create_copytrade_keyboard(copytrade_settings),
    )

    await state.set_state(CopyTradeStates.CREATING)

@router.callback_query(F.data == "set_fast_trade_duration", CopyTradeStates.CREATING)
async def start_set_fast_trade_duration(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    # Store original message details for later updates
    await state.update_data(
        original_message_id=callback.message.message_id,
        original_chat_id=callback.message.chat.id,
    )

    # Send prompt message with force reply
    msg = await callback.message.answer(
        "👋 请输入快速交易累计间隔（10-100000秒）：",
        parse_mode="HTML",
        reply_markup=ForceReply(),
    )

    # Store prompt message details for cleanup
    await state.update_data(
        prompt_message_id=msg.message_id,
        prompt_chat_id=msg.chat.id,
    )

    await state.set_state(CopyTradeStates.CREATE_WAITING_FOR_FAST_TRADE_DURATION)


@router.message(CopyTradeStates.CREATE_WAITING_FOR_FAST_TRADE_DURATION)
async def handle_set_fast_trade_duration(message: Message, state: FSMContext):
    if not message.text:
        return

    fast_trade_duration = message.text.strip()

    # Get stored data
    data = await state.get_data()
    copytrade_settings: CopyTrade | None = cast(
        CopyTrade | None, data.get("copytrade_settings")
    )

    if copytrade_settings is None:
        logger.warning("Copytrade settings not found in state")
        return

    try:
        fast_trade_duration = int(fast_trade_duration)
    except ValueError:
        msg = await message.reply(
            "❌ 无效的时间间隔，请重新输入：", reply_markup=ForceReply()
        )
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    if fast_trade_duration < 10 or fast_trade_duration > 100000:
        msg = await message.reply(
            "❌ 无效的时间间隔，请重新输入：", reply_markup=ForceReply()
        )
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    # Update settings
    copytrade_settings.fast_trade_duration = fast_trade_duration
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    # Clean up messages
    try:
        await message.delete()  # Delete user's input
        await message.bot.delete_message(  # Delete prompt message
            chat_id=data["prompt_chat_id"],
            message_id=data["prompt_message_id"],
        )
    except Exception as e:
        logger.warning(f"Failed to delete messages: {e}")

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=CREATE_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=create_copytrade_keyboard(copytrade_settings),
    )

    await state.set_state(CopyTradeStates.CREATING)


@router.callback_query(F.data == "set_fast_trade_sleep_threshold", CopyTradeStates.CREATING)
async def start_set_fast_trade_sleep_threshold(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    # Store original message details for later updates
    await state.update_data(
        original_message_id=callback.message.message_id,
        original_chat_id=callback.message.chat.id,
    )

    # Send prompt message with force reply
    msg = await callback.message.answer(
        "👋 请输入快速交易休眠阈值（1-1000次）：",
        parse_mode="HTML",
        reply_markup=ForceReply(),
    )

    # Store prompt message details for cleanup
    await state.update_data(
        prompt_message_id=msg.message_id,
        prompt_chat_id=msg.chat.id,
    )

    await state.set_state(CopyTradeStates.CREATE_WAITING_FOR_FAST_TRADE_SLEEP_THRESHOLD)


@router.message(CopyTradeStates.CREATE_WAITING_FOR_FAST_TRADE_SLEEP_THRESHOLD)
async def handle_set_fast_trade_sleep_threshold(message: Message, state: FSMContext):
    if not message.text:
        return

    fast_trade_sleep_threshold = message.text.strip()

    # Get stored data
    data = await state.get_data()
    copytrade_settings: CopyTrade | None = cast(
        CopyTrade | None, data.get("copytrade_settings")
    )

    if copytrade_settings is None:
        logger.warning("Copytrade settings not found in state")
        return

    try:
        fast_trade_sleep_threshold = int(fast_trade_sleep_threshold)
    except ValueError:
        msg = await message.reply(
            "❌ 无效的休眠阈值，请重新输入：", reply_markup=ForceReply()
        )
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    if fast_trade_sleep_threshold < 1 or fast_trade_sleep_threshold > 1000:
        msg = await message.reply(
            "❌ 无效的休眠阈值，请重新输入：", reply_markup=ForceReply()
        )
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    # Update settings
    copytrade_settings.fast_trade_sleep_threshold = fast_trade_sleep_threshold
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    # Clean up messages
    try:
        await message.delete()  # Delete user's input
        await message.bot.delete_message(  # Delete prompt message
            chat_id=data["prompt_chat_id"],
            message_id=data["prompt_message_id"],
        )
    except Exception as e:
        logger.warning(f"Failed to delete messages: {e}")

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=CREATE_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=create_copytrade_keyboard(copytrade_settings),
    )

    await state.set_state(CopyTradeStates.CREATING)

# 新增设置跟单缩放比例
@router.callback_query(F.data == "set_auto_buy_ratio", CopyTradeStates.CREATING)
async def start_set_auto_buy_ratio(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    # Store original message details for later updates
    await state.update_data(
        original_message_id=callback.message.message_id,
        original_chat_id=callback.message.chat.id,
    )

    # Send prompt message with force reply
    msg = await callback.message.answer(
        "👋 请输入跟单缩放比例（0-100，最多放大100倍）：",
        parse_mode="HTML",
        reply_markup=ForceReply(),
    )

    # Store prompt message details for cleanup
    await state.update_data(
        prompt_message_id=msg.message_id,
        prompt_chat_id=msg.chat.id,
    )

    await state.set_state(CopyTradeStates.CREATE_WAITING_FOR_AUTO_BUY_RATIO)


@router.message(CopyTradeStates.CREATE_WAITING_FOR_AUTO_BUY_RATIO)
async def handle_set_auto_buy_ratio(message: Message, state: FSMContext):
    if not message.text:
        return

    auto_buy_ratio = message.text.strip()

    # Get stored data
    data = await state.get_data()
    copytrade_settings: CopyTrade | None = cast(
        CopyTrade | None, data.get("copytrade_settings")
    )

    if copytrade_settings is None:
        logger.warning("Copytrade settings not found in state")
        return

    try:
        auto_buy_ratio = float(auto_buy_ratio)
    except ValueError:
        msg = await message.reply(
            "❌ 无效的买入比例，请重新输入：", reply_markup=ForceReply()
        )
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    if auto_buy_ratio <= 0 or auto_buy_ratio > 100:
        msg = await message.reply(
            "❌ 无效的买入比例，请重新输入：", reply_markup=ForceReply()
        )
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    # Update settings
    copytrade_settings.auto_buy_ratio = auto_buy_ratio
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    # Clean up messages
    try:
        await message.delete()  # Delete user's input
        await message.bot.delete_message(  # Delete prompt message
            chat_id=data["prompt_chat_id"],
            message_id=data["prompt_message_id"],
        )
    except Exception as e:
        logger.warning(f"Failed to delete messages: {e}")

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=CREATE_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=create_copytrade_keyboard(copytrade_settings),
    )

    await state.set_state(CopyTradeStates.CREATING)


@router.callback_query(F.data == "toggle_auto_buy", CopyTradeStates.CREATING)
async def toggle_auto_buy(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    # Get stored data
    data = await state.get_data()
    copytrade_settings: CopyTrade | None = cast(
        CopyTrade | None, data.get("copytrade_settings")
    )

    if copytrade_settings is None:
        logger.warning("Copytrade settings not found in state")
        return

    # if copytrade_settings.auto_buy is True:
    #     return

    copytrade_settings.auto_buy = not copytrade_settings.auto_buy
    await state.update_data(copytrade_settings=copytrade_settings)

    await callback.message.edit_text(
        CREATE_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=create_copytrade_keyboard(copytrade_settings),
    )

@router.callback_query(F.data == "toggle_auto_sell", CopyTradeStates.CREATING)
async def toggle_auto_sell(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    # Get stored data
    data = await state.get_data()
    copytrade_settings: CopyTrade | None = cast(
        CopyTrade | None, data.get("copytrade_settings")
    )

    if copytrade_settings is None:
        logger.warning("Copytrade settings not found in state")
        return

    # if copytrade_settings.auto_sell is True:
    #     return

    copytrade_settings.auto_sell = not copytrade_settings.auto_sell
    await state.update_data(copytrade_settings=copytrade_settings)

    await callback.message.edit_text(
        CREATE_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=create_copytrade_keyboard(copytrade_settings),
    )

@router.callback_query(F.data == "toggle_anti_fast_trade", CopyTradeStates.CREATING)
async def toggle_anti_fast_trade(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    # Get stored data
    data = await state.get_data()
    copytrade_settings: CopyTrade | None = cast(
        CopyTrade | None, data.get("copytrade_settings")
    )

    if copytrade_settings is None:
        logger.warning("Copytrade settings not found in state")
        return

    # if copytrade_settings.anti_fast_trade is True:
    #     return

    copytrade_settings.anti_fast_trade = not copytrade_settings.anti_fast_trade
    await state.update_data(copytrade_settings=copytrade_settings)

    await callback.message.edit_text(
        CREATE_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=create_copytrade_keyboard(copytrade_settings),
    )

######
@router.callback_query(F.data == "set_max_position", CopyTradeStates.CREATING)
async def start_set_max_position(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    # Store original message details for later updates
    await state.update_data(
        original_message_id=callback.message.message_id,
        original_chat_id=callback.message.chat.id,
    )

    # Send prompt message with force reply
    msg = await callback.message.answer(
        "👋 请输入最大仓位（0-1000）:",
        parse_mode="HTML",
        reply_markup=ForceReply(),
    )

    # Store prompt message details for cleanup
    await state.update_data(
        prompt_message_id=msg.message_id,
        prompt_chat_id=msg.chat.id,
    )

    await state.set_state(CopyTradeStates.CREATE_WAITING_FOR_MAX_POSITION)


@router.message(CopyTradeStates.CREATE_WAITING_FOR_MAX_POSITION)
async def handle_set_max_position(message: Message, state: FSMContext):
    if not message.text:
        return

    max_position = message.text.strip()

    # Get stored data
    data = await state.get_data()
    copytrade_settings: CopyTrade | None = cast(CopyTrade | None, data.get("copytrade_settings"))

    if copytrade_settings is None:
        logger.warning("Copytrade settings not found in state")
        return

    try:
        max_position = float(max_position)
    except ValueError:
        msg = await message.answer("❌ 无效的最大仓位，请重新输入：", reply_markup=ForceReply())
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    if max_position <= 0 or max_position > 1000:
        msg = await message.answer("❌ 无效的最大仓位，请重新输入：", reply_markup=ForceReply())
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    # Update settings
    copytrade_settings.max_position = int(max_position * 10 ** SOL_DECIMAL)
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    # Clean up messages
    try:
        await message.delete()  # Delete user's input
        await message.bot.delete_message(  # Delete prompt message
            chat_id=data["prompt_chat_id"],
            message_id=data["prompt_message_id"],
        )
    except Exception as e:
        logger.warning(f"Failed to delete messages: {e}")

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=CREATE_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=create_copytrade_keyboard(copytrade_settings),
    )

    await state.set_state(CopyTradeStates.CREATING)

######

@router.callback_query(F.data == "set_priority", CopyTradeStates.CREATING)
async def start_set_priority(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    # Store original message details for later updates
    await state.update_data(
        original_message_id=callback.message.message_id,
        original_chat_id=callback.message.chat.id,
    )

    # Send prompt message with force reply
    msg = await callback.message.answer(
        "👋 请输入优先费用（0-1）:",
        parse_mode="HTML",
        reply_markup=ForceReply(),
    )

    # Store prompt message details for cleanup
    await state.update_data(
        prompt_message_id=msg.message_id,
        prompt_chat_id=msg.chat.id,
    )

    await state.set_state(CopyTradeStates.CREATE_WAITING_FOR_PRIORITY)


@router.message(CopyTradeStates.CREATE_WAITING_FOR_PRIORITY)
async def handle_set_priority(message: Message, state: FSMContext):
    if not message.text:
        return

    priority = message.text.strip()

    # Get stored data
    data = await state.get_data()
    copytrade_settings: CopyTrade | None = cast(CopyTrade | None, data.get("copytrade_settings"))

    if copytrade_settings is None:
        logger.warning("Copytrade settings not found in state")
        return

    try:
        priority = float(priority)
    except ValueError:
        msg = await message.answer("❌ 无效的优先费用，请重新输入：", reply_markup=ForceReply())
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    if priority <= 0 or priority > 1:
        msg = await message.answer("❌ 无效的优先费用，请重新输入：", reply_markup=ForceReply())
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    # Update settings
    copytrade_settings.priority = int(priority * 10 ** SOL_DECIMAL)
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    # Clean up messages
    try:
        await message.delete()  # Delete user's input
        await message.bot.delete_message(  # Delete prompt message
            chat_id=data["prompt_chat_id"],
            message_id=data["prompt_message_id"],
        )
    except Exception as e:
        logger.warning(f"Failed to delete messages: {e}")

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=CREATE_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=create_copytrade_keyboard(copytrade_settings),
    )

    await state.set_state(CopyTradeStates.CREATING)


@router.callback_query(F.data == "toggle_anti_sandwich", CopyTradeStates.CREATING)
async def toggle_anti_sandwich(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    # Get stored data
    data = await state.get_data()
    copytrade_settings: CopyTrade | None = cast(CopyTrade | None, data.get("copytrade_settings"))

    if copytrade_settings is None:
        logger.warning("Copytrade settings not found in state")
        return

    copytrade_settings.anti_sandwich = not copytrade_settings.anti_sandwich
    await state.update_data(copytrade_settings=copytrade_settings)

    await callback.message.edit_text(
        CREATE_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=create_copytrade_keyboard(copytrade_settings),
    )


@router.callback_query(F.data == "toggle_auto_slippage", CopyTradeStates.CREATING)
async def toggle_auto_slippage(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    # Get stored data
    data = await state.get_data()
    copytrade_settings: CopyTrade | None = cast(CopyTrade | None, data.get("copytrade_settings"))

    if copytrade_settings is None:
        logger.warning("Copytrade settings not found in state")
        return

    copytrade_settings.auto_slippage = not copytrade_settings.auto_slippage
    await state.update_data(copytrade_settings=copytrade_settings)

    await callback.message.edit_text(
        CREATE_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=create_copytrade_keyboard(copytrade_settings),
    )


@router.callback_query(F.data == "set_custom_slippage", CopyTradeStates.CREATING)
async def start_set_custom_slippage(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    # Store original message details for later updates
    await state.update_data(
        original_message_id=callback.message.message_id,
        original_chat_id=callback.message.chat.id,
    )

    # Send prompt message with force reply
    msg = await callback.message.answer(
        "👋 请输入自定义滑点：（0-1）",
        parse_mode="HTML",
        reply_markup=ForceReply(),
    )

    # Store prompt message details for cleanup
    await state.update_data(
        prompt_message_id=msg.message_id,
        prompt_chat_id=msg.chat.id,
    )

    await state.set_state(CopyTradeStates.CREATE_WAITING_FOR_CUSTOM_SLIPPAGE)


@router.message(CopyTradeStates.CREATE_WAITING_FOR_CUSTOM_SLIPPAGE)
async def handle_set_custom_slippage(message: Message, state: FSMContext):
    if not message.text:
        return

    custom_slippage = message.text.strip()

    # Get stored data
    data = await state.get_data()
    copytrade_settings: CopyTrade | None = cast(CopyTrade | None, data.get("copytrade_settings"))

    if copytrade_settings is None:
        logger.warning("Copytrade settings not found in state")
        return

    try:
        custom_slippage = float(custom_slippage)
    except ValueError:
        msg = await message.reply("❌ 无效的自定义滑点，请重新输入：", reply_markup=ForceReply())
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    if custom_slippage <= 0 or custom_slippage > 1:
        msg = await message.reply("❌ 无效的自定义滑点，请重新输入：", reply_markup=ForceReply())
        await state.update_data(prompt_message_id=msg.message_id)
        await state.update_data(prompt_chat_id=msg.chat.id)
        if message.bot is not None:
            await message.delete()
            await message.bot.delete_message(  # Delete prompt message
                chat_id=data["prompt_chat_id"],
                message_id=data["prompt_message_id"],
            )
        return

    # Update settings
    copytrade_settings.custom_slippage = custom_slippage
    copytrade_settings.auto_slippage = False
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    # Clean up messages
    try:
        await message.delete()  # Delete user's input
        await message.bot.delete_message(  # Delete prompt message
            chat_id=data["prompt_chat_id"],
            message_id=data["prompt_message_id"],
        )
    except Exception as e:
        logger.warning(f"Failed to delete messages: {e}")

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=CREATE_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=create_copytrade_keyboard(copytrade_settings),
    )

    await state.set_state(CopyTradeStates.CREATING)


@router.callback_query(F.data == "back_to_copytrade", CopyTradeStates.CREATING)
async def cancel_copytrade(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    data = await render(callback)
    await callback.message.edit_text(**data)
    await state.set_state(CopyTradeStates.MENU)


@router.callback_query(F.data == "submit_copytrade", CopyTradeStates.CREATING)
async def submit_copytrade(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    # Get stored data
    data = await state.get_data()
    copytrade_settings: CopyTrade | None = cast(CopyTrade | None, data.get("copytrade_settings"))

    if copytrade_settings is None:
        logger.warning("Copytrade settings not found in state")
        return

    # Validate copytrade settings
    if copytrade_settings.target_wallet is None:
        # 发送错误消息并在 10 秒后删除
        error_message = await callback.message.answer("❌ 创建失败，请设置正确的跟单地址")

        # 创建一个异步任务来删除消息
        async def delete_message_later(message: Message, delay: int):
            await asyncio.sleep(delay)
            try:
                await message.delete()
            except Exception as e:
                logger.warning(f"Failed to delete message: {e}")

        delete_task = asyncio.create_task(delete_message_later(error_message, 10))
        # 添加任务完成回调以处理可能的异常
        delete_task.add_done_callback(lambda t: t.exception() if t.exception() else None)
        return

    # 写入数据库
    try:
        await copy_trade_service.add(copytrade_settings)
    except Exception as e:
        logger.warning(f"Failed to add copytrade: {e}")
        # 发送错误消息并在 10 秒后删除
        error_message = await callback.message.answer("❌ 创建失败，请稍后重试")

        # 创建一个异步任务来删除消息
        async def delete_message_later(message: Message, delay: int):
            await asyncio.sleep(delay)
            try:
                await message.delete()
            except Exception as e:
                logger.warning(f"Failed to delete message: {e}")

        delete_task = asyncio.create_task(delete_message_later(error_message, 10))
        # 添加任务完成回调以处理可能的异常
        delete_task.add_done_callback(lambda t: t.exception() if t.exception() else None)
        return

    data = await render(callback)
    await callback.message.edit_text(**data)
    await state.set_state(CopyTradeStates.MENU)
    logger.info(f"Copytrade created successfully, id: {copytrade_settings}")

import re
from typing import cast

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ForceReply, Message
from solbot_common.log import logger
from solbot_common.types.copytrade import CopyTrade
from solbot_common.constants import SOL_DECIMAL

from tg_bot.conversations.copytrade.render import render
from tg_bot.conversations.states import CopyTradeStates
from tg_bot.keyboards.common import back_keyboard, confirm_keyboard
from tg_bot.keyboards.copytrade import edit_copytrade_keyboard
from tg_bot.services.copytrade import CopyTradeService
from tg_bot.templates import EDIT_COPYTRADE_MESSAGE
from tg_bot.utils import cleanup_conversation_messages

router = Router()
copy_trade_service = CopyTradeService()

# Regular expression to match copytrade_{id} pattern
COPYTRADE_PATTERN = re.compile(r"copytrade_(\d+)")


@router.callback_query(lambda c: COPYTRADE_PATTERN.match(c.data))
async def handle_copytrade_selection(callback: CallbackQuery, state: FSMContext):
    """Handle selection of a specific copytrade item"""
    if callback.message is None:
        return

    if not isinstance(callback.message, Message):
        return

    if callback.data is None:
        logger.warning("No data found in callback")
        return

    # Extract the copytrade ID from callback data
    match = COPYTRADE_PATTERN.match(callback.data)
    if not match:
        logger.warning("Invalid callback data for copytrade selection")
        return

    copytrade_id = int(match.group(1))

    # Fetch the copytrade data
    copytrade = await copy_trade_service.get_by_id(copytrade_id)
    copytrade_settings = copytrade
    if copytrade is None:
        await callback.answer("❌ 跟单不存在或已被删除")
        return

    # Store copytrade ID in state
    await state.update_data(copytrade_id=copytrade_id)
    await state.update_data(copytrade_settings=copytrade_settings)

    # Show edit keyboard for the selected copytrade
    keyboard = edit_copytrade_keyboard(copytrade)
    await callback.message.edit_text(text=EDIT_COPYTRADE_MESSAGE, reply_markup=keyboard)
    await state.set_state(CopyTradeStates.EDITING)


@router.callback_query(F.data == "set_target_alias", CopyTradeStates.EDITING)
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

    await state.set_state(CopyTradeStates.EDIT_WAITING_FOR_ALIAS)


@router.message(CopyTradeStates.EDIT_WAITING_FOR_ALIAS)
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

    # Check if alias has changed
    if copytrade_settings.target_alias == alias:
        await state.set_state(CopyTradeStates.EDITING)
        await cleanup_conversation_messages(message, state)
        return

    # Update settings
    copytrade_settings.target_alias = alias
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    # Clean up messages
    await cleanup_conversation_messages(message, state)

    # Save changes to the database
    await copy_trade_service.update(copytrade_settings)

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=EDIT_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=edit_copytrade_keyboard(copytrade_settings),
    )

    await state.set_state(CopyTradeStates.EDITING)

# 新增编辑属性
@router.callback_query(F.data == "set_filter_min_buy", CopyTradeStates.EDITING)
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

    await state.set_state(CopyTradeStates.EDIT_WAITING_FOR_FILTER_MIN_BUY)


@router.message(CopyTradeStates.EDIT_WAITING_FOR_FILTER_MIN_BUY)
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

    # Check if filter_min_buy has changed
    if copytrade_settings.filter_min_buy == int(filter_min_buy * 10 ** 9):
        await state.set_state(CopyTradeStates.EDITING)
        await cleanup_conversation_messages(message, state)
        return

    # Update settings
    copytrade_settings.filter_min_buy = int(filter_min_buy * 10 ** 9)
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    try:
        await copy_trade_service.update(copytrade_settings)
    except Exception as e:
        logger.warning(f"Failed to update copytrade: {e}")
        return

    # Clean up messages
    await cleanup_conversation_messages(message, state)
    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=EDIT_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=edit_copytrade_keyboard(copytrade_settings),
    )

    await state.set_state(CopyTradeStates.EDITING)


@router.callback_query(F.data == "set_max_buy_time", CopyTradeStates.EDITING)
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

    await state.set_state(CopyTradeStates.EDIT_WAITING_FOR_MAX_BUY_TIME)


@router.message(CopyTradeStates.EDIT_WAITING_FOR_MAX_BUY_TIME)
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

    # Check if max_buy_time has changed
    if copytrade_settings.max_buy_time == max_buy_time:
        await state.set_state(CopyTradeStates.EDITING)
        await cleanup_conversation_messages(message, state)
        return

    # Update settings
    copytrade_settings.max_buy_time = max_buy_time
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    try:
        await copy_trade_service.update(copytrade_settings)
    except Exception as e:
        logger.warning(f"Failed to update copytrade: {e}")
        return

    # Clean up messages
    await cleanup_conversation_messages(message, state)

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=EDIT_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=edit_copytrade_keyboard(copytrade_settings),
    )
    await state.set_state(CopyTradeStates.EDITING)

@router.callback_query(F.data == "set_fast_trade_sleep_time", CopyTradeStates.EDITING)
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
        "👋 请输入防割睡眠时间（1-100000）：",
        parse_mode="HTML",
        reply_markup=ForceReply(),
    )

    # Store prompt message details for cleanup
    await state.update_data(
        prompt_message_id=msg.message_id,
        prompt_chat_id=msg.chat.id,
    )

    await state.set_state(CopyTradeStates.EDIT_WAITING_FOR_FAST_TRADE_SLEEP_TIME)


@router.message(CopyTradeStates.EDIT_WAITING_FOR_FAST_TRADE_SLEEP_TIME)
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
            "❌ 无效的睡眠时长，请重新输入：", reply_markup=ForceReply()
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
            "❌ 无效的睡眠时长，请重新输入：", reply_markup=ForceReply()
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

    # Check if fast_trade_sleep_time has changed
    if copytrade_settings.fast_trade_sleep_time == fast_trade_sleep_time:
        await state.set_state(CopyTradeStates.EDITING)
        await cleanup_conversation_messages(message, state)
        return

    # Update settings
    copytrade_settings.fast_trade_sleep_time = fast_trade_sleep_time
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    try:
        await copy_trade_service.update(copytrade_settings)
    except Exception as e:
        logger.warning(f"Failed to update copytrade: {e}")
        return

    # Clean up messages
    await cleanup_conversation_messages(message, state)

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=EDIT_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=edit_copytrade_keyboard(copytrade_settings),
    )
    await state.set_state(CopyTradeStates.EDITING)


@router.callback_query(F.data == "set_min_buy_sol", CopyTradeStates.EDITING)
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

    await state.set_state(CopyTradeStates.EDIT_WAITING_FOR_MIN_BUY_SOL)


@router.message(CopyTradeStates.EDIT_WAITING_FOR_MIN_BUY_SOL)
async def handle_set_min_buy_sol(message: Message, state: FSMContext):
    if not message.text:
        return

    min_buy_sol = message.text.strip()

    # Get stored data
    data = await state.get_data()
    copytrade_settings: CopyTrade | None = cast(CopyTrade | None, data.get("copytrade_settings"))

    if copytrade_settings is None:
        logger.warning("Copytrade settings not found in state")
        return

    try:
        min_buy_sol = float(min_buy_sol)
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

    if min_buy_sol < 0 or min_buy_sol > 100:
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

    # Check if min_buy_sol has changed
    if copytrade_settings.min_buy_sol == int(min_buy_sol * 10 ** 9):
        await state.set_state(CopyTradeStates.EDITING)
        await cleanup_conversation_messages(message, state)
        return

    # Update settings
    copytrade_settings.min_buy_sol = int(min_buy_sol * 10 ** 9)
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    try:
        await copy_trade_service.update(copytrade_settings)
    except Exception as e:
        logger.warning(f"Failed to update copytrade: {e}")
        return

    # Clean up messages
    await cleanup_conversation_messages(message, state)

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=EDIT_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=edit_copytrade_keyboard(copytrade_settings),
    )

    await state.set_state(CopyTradeStates.EDITING)


@router.callback_query(F.data == "set_max_buy_sol", CopyTradeStates.EDITING)
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

    await state.set_state(CopyTradeStates.EDIT_WAITING_FOR_MAX_BUY_SOL)


@router.message(CopyTradeStates.EDIT_WAITING_FOR_MAX_BUY_SOL)
async def handle_set_max_buy_sol(message: Message, state: FSMContext):
    if not message.text:
        return

    max_buy_sol = message.text.strip()
    # Get stored data
    data = await state.get_data()
    copytrade_settings: CopyTrade | None = cast(CopyTrade | None, data.get("copytrade_settings"))

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

    # Check if max_buy_sol has changed
    if copytrade_settings.max_buy_sol == int(max_buy_sol * 10 ** 9):
        await state.set_state(CopyTradeStates.EDITING)
        await cleanup_conversation_messages(message, state)
        return

    # Update settings
    copytrade_settings.max_buy_sol = int(max_buy_sol * 10 ** 9)
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    try:
        await copy_trade_service.update(copytrade_settings)
    except Exception as e:
        logger.warning(f"Failed to update copytrade: {e}")
        return

    # Clean up messages
    await cleanup_conversation_messages(message, state)

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=EDIT_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=edit_copytrade_keyboard(copytrade_settings),
    )

    await state.set_state(CopyTradeStates.EDITING)

@router.callback_query(F.data == "set_min_sell_ratio", CopyTradeStates.EDITING)
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

    await state.set_state(CopyTradeStates.EDIT_WAITING_FOR_MIN_SELL_RATIO)


@router.message(CopyTradeStates.EDIT_WAITING_FOR_MIN_SELL_RATIO)
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

    # Check if min_sell_ratio has changed
    if copytrade_settings.min_sell_ratio == min_sell_ratio:
        await state.set_state(CopyTradeStates.EDITING)
        await cleanup_conversation_messages(message, state)
        return

    # Update settings
    copytrade_settings.min_sell_ratio = min_sell_ratio
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    try:
        await copy_trade_service.update(copytrade_settings)
    except Exception as e:
        logger.warning(f"Failed to update copytrade: {e}")
        return

    # Clean up messages
    await cleanup_conversation_messages(message, state)

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=EDIT_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=edit_copytrade_keyboard(copytrade_settings),
    )

    await state.set_state(CopyTradeStates.EDITING)

@router.callback_query(F.data == "set_fast_trade_threshold", CopyTradeStates.EDITING)
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

    await state.set_state(CopyTradeStates.EDIT_WAITING_FOR_FAST_TRADE_THRESHOLD)


@router.message(CopyTradeStates.EDIT_WAITING_FOR_FAST_TRADE_THRESHOLD)
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

    # Check if fast_trade_threshold has changed
    if copytrade_settings.fast_trade_threshold == fast_trade_threshold:
        await state.set_state(CopyTradeStates.EDITING)
        await cleanup_conversation_messages(message, state)
        return

    # Update settings
    copytrade_settings.fast_trade_threshold = fast_trade_threshold
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    try:
        await copy_trade_service.update(copytrade_settings)
    except Exception as e:
        logger.warning(f"Failed to update copytrade: {e}")
        return

    # Clean up messages
    await cleanup_conversation_messages(message, state)

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=EDIT_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=edit_copytrade_keyboard(copytrade_settings),
    )

    await state.set_state(CopyTradeStates.EDITING)

@router.callback_query(F.data == "set_fast_trade_duration", CopyTradeStates.EDITING)
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

    await state.set_state(CopyTradeStates.EDIT_WAITING_FOR_FAST_TRADE_DURATION)


@router.message(CopyTradeStates.EDIT_WAITING_FOR_FAST_TRADE_DURATION)
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

    # Check if fast_trade_duration has changed
    if copytrade_settings.fast_trade_duration == fast_trade_duration:
        await state.set_state(CopyTradeStates.EDITING)
        await cleanup_conversation_messages(message, state)
        return

    # Update settings
    copytrade_settings.fast_trade_duration = fast_trade_duration
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    try:
        await copy_trade_service.update(copytrade_settings)
    except Exception as e:
        logger.warning(f"Failed to update copytrade: {e}")
        return

    # Clean up messages
    await cleanup_conversation_messages(message, state)

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=EDIT_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=edit_copytrade_keyboard(copytrade_settings),
    )

    await state.set_state(CopyTradeStates.EDITING)


@router.callback_query(F.data == "set_fast_trade_sleep_threshold", CopyTradeStates.EDITING)
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

    await state.set_state(CopyTradeStates.EDIT_WAITING_FOR_FAST_TRADE_SLEEP_THRESHOLD)


@router.message(CopyTradeStates.EDIT_WAITING_FOR_FAST_TRADE_SLEEP_THRESHOLD)
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

    # Check if fast_trade_sleep_threshold has changed
    if copytrade_settings.fast_trade_sleep_threshold == fast_trade_sleep_threshold:
        await state.set_state(CopyTradeStates.EDITING)
        await cleanup_conversation_messages(message, state)
        return

    # Update settings
    copytrade_settings.fast_trade_sleep_threshold = fast_trade_sleep_threshold
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    try:
        await copy_trade_service.update(copytrade_settings)
    except Exception as e:
        logger.warning(f"Failed to update copytrade: {e}")
        return

    # Clean up messages
    await cleanup_conversation_messages(message, state)

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=EDIT_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=edit_copytrade_keyboard(copytrade_settings),
    )

    await state.set_state(CopyTradeStates.EDITING)

# 新增编辑跟单缩放比例
@router.callback_query(F.data == "set_auto_buy_ratio", CopyTradeStates.EDITING)
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

    await state.set_state(CopyTradeStates.EDIT_WAITING_FOR_AUTO_BUY_RATIO)


@router.message(CopyTradeStates.EDIT_WAITING_FOR_AUTO_BUY_RATIO)
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

    # Check if auto_buy_ratio has changed
    if copytrade_settings.auto_buy_ratio == auto_buy_ratio:
        await state.set_state(CopyTradeStates.EDITING)
        await cleanup_conversation_messages(message, state)
        return

    # Update settings
    copytrade_settings.auto_buy_ratio = auto_buy_ratio
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    try:
        await copy_trade_service.update(copytrade_settings)
    except Exception as e:
        logger.warning(f"Failed to update copytrade: {e}")
        return

    # Clean up messages
    await cleanup_conversation_messages(message, state)

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=EDIT_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=edit_copytrade_keyboard(copytrade_settings),
    )

    await state.set_state(CopyTradeStates.EDITING)

@router.callback_query(F.data == "toggle_auto_buy", CopyTradeStates.EDITING)
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

    copytrade_settings.auto_buy = not copytrade_settings.auto_buy
    await state.update_data(copytrade_settings=copytrade_settings)
    try:
        await copy_trade_service.update(copytrade_settings)
    except Exception as e:
        logger.warning(f"Failed to update copytrade: {e}")
        return

    await callback.message.edit_text(
        EDIT_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=edit_copytrade_keyboard(copytrade_settings),
    )

@router.callback_query(F.data == "toggle_auto_sell", CopyTradeStates.EDITING)
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

    copytrade_settings.auto_sell = not copytrade_settings.auto_sell
    await state.update_data(copytrade_settings=copytrade_settings)
    try:
        await copy_trade_service.update(copytrade_settings)
    except Exception as e:
        logger.warning(f"Failed to update copytrade: {e}")
        return

    await callback.message.edit_text(
        EDIT_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=edit_copytrade_keyboard(copytrade_settings),
    )

@router.callback_query(F.data == "toggle_anti_fast_trade", CopyTradeStates.EDITING)
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

    copytrade_settings.anti_fast_trade = not copytrade_settings.anti_fast_trade
    await state.update_data(copytrade_settings=copytrade_settings)
    try:
        await copy_trade_service.update(copytrade_settings)
    except Exception as e:
        logger.warning(f"Failed to update copytrade: {e}")
        return

    await callback.message.edit_text(
        EDIT_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=edit_copytrade_keyboard(copytrade_settings),
    )

######
@router.callback_query(F.data == "set_max_position", CopyTradeStates.EDITING)
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

    await state.set_state(CopyTradeStates.EDIT_WAITING_FOR_MAX_POSITION)


@router.message(CopyTradeStates.EDIT_WAITING_FOR_MAX_POSITION)
async def handle_set_max_position(message: Message, state: FSMContext):
    if not message.text:
        return

    max_position = message.text.strip()

    # Get stored data
    data = await state.get_data()
    copytrade_settings: CopyTrade | None = cast(
        CopyTrade | None, data.get("copytrade_settings")
    )

    if copytrade_settings is None:
        logger.warning("Copytrade settings not found in state")
        return

    try:
        max_position = float(max_position)
    except ValueError:
        msg = await message.reply(
            "❌ 无效的最大仓位，请重新输入：", reply_markup=ForceReply()
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

    if max_position <= 0 or max_position > 1000:
        msg = await message.reply(
            "❌ 无效的最大仓位，请重新输入：", reply_markup=ForceReply()
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

    # Check if max_position has changed
    if copytrade_settings.max_position == int(max_position * 10 ** SOL_DECIMAL):
        await state.set_state(CopyTradeStates.EDITING)
        await cleanup_conversation_messages(message, state)
        return

    # Update settings
    copytrade_settings.max_position = int(max_position * 10 ** SOL_DECIMAL)
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    # Clean up messages
    await cleanup_conversation_messages(message, state)

    try:
        await copy_trade_service.update(copytrade_settings)
    except Exception as e:
        logger.warning(f"Failed to update copytrade: {e}")
        return

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=EDIT_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=edit_copytrade_keyboard(copytrade_settings),
    )

    await state.set_state(CopyTradeStates.EDITING)
######

@router.callback_query(F.data == "set_priority", CopyTradeStates.EDITING)
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

    await state.set_state(CopyTradeStates.EDIT_WAITING_FOR_PRIORITY)


@router.message(CopyTradeStates.EDIT_WAITING_FOR_PRIORITY)
async def handle_set_priority(message: Message, state: FSMContext):
    if not message.text:
        return

    priority = message.text.strip()

    # Get stored data
    data = await state.get_data()
    copytrade_settings: CopyTrade | None = cast(
        CopyTrade | None, data.get("copytrade_settings")
    )

    if copytrade_settings is None:
        logger.warning("Copytrade settings not found in state")
        return

    try:
        priority = float(priority)
    except ValueError:
        msg = await message.reply(
            "❌ 无效的优先费用，请重新输入：", reply_markup=ForceReply()
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

    if priority <= 0 or priority > 1:
        msg = await message.reply(
            "❌ 无效的优先费用，请重新输入：", reply_markup=ForceReply()
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

    # Check if priority has changed
    if copytrade_settings.priority == int(priority * 10 ** SOL_DECIMAL):
        await state.set_state(CopyTradeStates.EDITING)
        await cleanup_conversation_messages(message, state)
        return

    # Update settings
    copytrade_settings.priority = int(priority * 10 ** SOL_DECIMAL)
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    # Clean up messages
    await cleanup_conversation_messages(message, state)

    try:
        await copy_trade_service.update(copytrade_settings)
    except Exception as e:
        logger.warning(f"Failed to update copytrade: {e}")
        return

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=EDIT_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=edit_copytrade_keyboard(copytrade_settings),
    )

    await state.set_state(CopyTradeStates.EDITING)


@router.callback_query(F.data == "toggle_anti_sandwich", CopyTradeStates.EDITING)
async def toggle_anti_sandwich(callback: CallbackQuery, state: FSMContext):
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

    copytrade_settings.anti_sandwich = not copytrade_settings.anti_sandwich
    await state.update_data(copytrade_settings=copytrade_settings)
    try:
        await copy_trade_service.update(copytrade_settings)
    except Exception as e:
        logger.warning(f"Failed to update copytrade: {e}")
        return

    await callback.message.edit_text(
        EDIT_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=edit_copytrade_keyboard(copytrade_settings),
    )


@router.callback_query(F.data == "toggle_auto_slippage", CopyTradeStates.EDITING)
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

    try:
        await copy_trade_service.update(copytrade_settings)
    except Exception as e:
        logger.warning(f"Failed to update copytrade: {e}")
        return

    await callback.message.edit_text(
        EDIT_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=edit_copytrade_keyboard(copytrade_settings),
    )


@router.callback_query(F.data == "set_custom_slippage", CopyTradeStates.EDITING)
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
        "👋 请输入自定义滑点（0-1）：",
        parse_mode="HTML",
        reply_markup=ForceReply(),
    )

    # Store prompt message details for cleanup
    await state.update_data(
        prompt_message_id=msg.message_id,
        prompt_chat_id=msg.chat.id,
    )

    await state.set_state(CopyTradeStates.EDIT_WAITING_FOR_CUSTOM_SLIPPAGE)


@router.message(CopyTradeStates.EDIT_WAITING_FOR_CUSTOM_SLIPPAGE)
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

    if copytrade_settings.custom_slippage == custom_slippage:
        await state.set_state(CopyTradeStates.EDITING)
        await cleanup_conversation_messages(message, state)
        return

    # Update settings
    copytrade_settings.custom_slippage = custom_slippage
    copytrade_settings.auto_slippage = False
    await state.update_data(copytrade_settings=copytrade_settings)

    if message.bot is None:
        logger.warning("No bot found in message")
        return

    # Clean up messages
    await cleanup_conversation_messages(message, state)

    try:
        await copy_trade_service.update(copytrade_settings)
    except Exception as e:
        logger.warning(f"Failed to update copytrade: {e}")
        return

    await message.bot.edit_message_text(
        chat_id=data["original_chat_id"],
        message_id=data["original_message_id"],
        text=EDIT_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=edit_copytrade_keyboard(copytrade_settings),
    )

    await state.set_state(CopyTradeStates.EDITING)


@router.callback_query(F.data == "delete_copytrade", CopyTradeStates.EDITING)
async def delete_copytrade(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    # 记录当前消息，如果后续确认删除的话，当前这条消息也需要被删除
    await state.update_data(
        original_message_id=callback.message.message_id,
        original_chat_id=callback.message.chat.id,
    )

    text = "⚠️ 您正在删除一个跟单交易, 请您确认:"
    await callback.message.reply(
        text,
        parse_mode="HTML",
        reply_markup=confirm_keyboard("confirm_delete_copytrade", "cancel_delete_copytrade"),
    )


@router.callback_query(F.data == "confirm_delete_copytrade", CopyTradeStates.EDITING)
async def confirm_delete_copytrade(callback: CallbackQuery, state: FSMContext):
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

    await copy_trade_service.delete(copytrade_settings)

    # 删除 原始消息
    original_message_id = data.get("original_message_id")
    original_chat_id = data.get("original_chat_id")
    if (
        original_message_id is not None
        and original_chat_id is not None
        and callback.message.bot is not None
    ):
        await callback.message.bot.delete_message(
            chat_id=original_chat_id, message_id=original_message_id
        )

    # 发送删除成功的消息
    await callback.message.edit_text(
        "✅ 您已成功删除一个跟单交易",
        parse_mode="HTML",
        reply_markup=back_keyboard("back_to_copytrade"),
    )
    # clear copytrade data
    await state.update_data(copytrade_id=None)
    await state.update_data(copytrade_settings=None)


@router.callback_query(F.data == "cancel_delete_copytrade", CopyTradeStates.EDITING)
async def cancel_delete_copytrade(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    # 删除 确认消息
    await callback.message.delete()


@router.callback_query(F.data == "toggle_copytrade", CopyTradeStates.EDITING)
async def toggle_copytrade(callback: CallbackQuery, state: FSMContext):
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

    copytrade_settings.active = not copytrade_settings.active
    await state.update_data(copytrade_settings=copytrade_settings)

    try:
        await copy_trade_service.update(copytrade_settings)
    except Exception as e:
        logger.warning(f"Failed to update copytrade: {e}")
        return

    await callback.message.edit_text(
        EDIT_COPYTRADE_MESSAGE,
        parse_mode="HTML",
        reply_markup=edit_copytrade_keyboard(copytrade_settings),
    )


@router.callback_query(F.data == "back_to_copytrade", CopyTradeStates.EDITING)
async def back_to_copytrade(callback: CallbackQuery, state: FSMContext):
    if callback.message is None:
        logger.warning("No message found in update")
        return

    if not isinstance(callback.message, Message):
        logger.warning("Message is not a Message object")
        return

    # clear copytrade data
    await state.update_data(copytrade_id=None)
    await state.update_data(copytrade_settings=None)

    data = await render(callback)
    await callback.message.edit_text(**data)
    await state.set_state(CopyTradeStates.MENU)

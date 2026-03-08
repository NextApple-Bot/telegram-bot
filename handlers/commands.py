from aiogram import F
from aiogram.types import Message
from aiogram.filters import Command

from .base import (
    router, logger, show_inventory, start_upload_selection,
    cancel_action, get_main_menu_keyboard, show_help, UploadStates, process_full_text
)

@router.message(Command("start"))
async def cmd_start(message: Message, bot):
    logger.info(f"🔥 Команда /start получена от {message.from_user.id}")
    try:
        keyboard = get_main_menu_keyboard()
        await message.answer(
            "👋 Добро пожаловать! Используйте кнопки ниже для управления.",
            reply_markup=keyboard
        )
        logger.info(f"✅ Ответ на /start отправлен пользователю {message.from_user.id}")
    except Exception as e:
        logger.exception(f"❌ Ошибка при обработке /start: {e}")

@router.message(Command("inventory"))
async def cmd_inventory(message: Message, bot):
    await show_inventory(bot, message.chat.id)

@router.message(Command("upload"))
async def cmd_upload(message: Message, bot, state):
    await start_upload_selection(message, bot, state, message.from_user.id)

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, bot, state):
    await cancel_action(bot, message.chat.id, state)
    await message.answer("Главное меню:", reply_markup=get_main_menu_keyboard())

@router.message(Command("help"))
async def cmd_help(message: Message, bot):
    await show_help(bot, message.chat.id)

@router.message(Command("done"))
async def cmd_done(message: Message, bot, state):
    current_state = await state.get_state()
    if current_state != UploadStates.waiting_for_inventory.state:
        await message.answer("❌ Сейчас нет накопленных данных для завершения.")
        return
    data = await state.get_data()
    parts = data.get("parts", [])
    mode = data.get("mode")
    if not parts:
        await message.answer("❌ Нет ни одной части для обработки. Отправьте текст или используйте /cancel.")
        return
    full_text = "\n".join(parts)
    await process_full_text(message, full_text, mode, state, bot)

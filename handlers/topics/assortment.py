import re
import tempfile
import os
import aiofiles
from aiogram import F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import config
import inventory
from sort_assortment import sort_assortment_to_categories
from handlers.states import AssortmentConfirmState

router = Router()
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

@router.message(F.chat.id == config.MAIN_GROUP_ID, F.message_thread_id == config.THREAD_ASSORTMENT)
async def handle_assortment_upload(message: Message, bot, state: FSMContext):
    """Обрабатывает загрузку нового ассортимента (текст или файл)."""
    if message.text:
        full_text = message.text.strip()
        if not full_text:
            await message.reply("❌ Пустой список.")
            return
        categories = sort_assortment_to_categories(full_text)
        if not categories:
            await message.reply("❌ Не удалось распознать ни одной категории.")
            return
        await state.update_data(temp_categories=categories)
        await state.set_state(AssortmentConfirmState.waiting_for_confirm)
        total_items = sum(len(cat['items']) for cat in categories)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="assort_confirm:yes"),
             InlineKeyboardButton(text="❌ Отмена", callback_data="assort_confirm:no")]
        ])
        await message.reply(
            f"📦 Найдено категорий: {len(categories)}, всего позиций: {total_items}\n"
            "Подтвердите загрузку (это заменит весь текущий ассортимент).",
            reply_markup=keyboard
        )
    elif message.document:
        document = message.document
        if document.file_size > MAX_FILE_SIZE:
            await message.reply("❌ Файл слишком большой (макс. 10 МБ).")
            return
        if not (document.mime_type == 'text/plain' or document.file_name.endswith('.txt')):
            await message.reply("⚠️ Отправьте текстовый файл .txt")
            return
        file_path = f"/tmp/{document.file_name}"
        await bot.download(document, destination=file_path)
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
            if not content.strip():
                await message.reply("❌ Файл пуст.")
                return
            categories = sort_assortment_to_categories(content)
            if not categories:
                await message.reply("❌ Не удалось распознать ни одной категории.")
                return
            await state.update_data(temp_categories=categories)
            await state.set_state(AssortmentConfirmState.waiting_for_confirm)
            total_items = sum(len(cat['items']) for cat in categories)
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Подтвердить", callback_data="assort_confirm:yes"),
                 InlineKeyboardButton(text="❌ Отмена", callback_data="assort_confirm:no")]
            ])
            await message.reply(
                f"📦 Найдено категорий: {len(categories)}, всего позиций: {total_items}\n"
                "Подтвердите загрузку (это заменит весь текущий ассортимент).",
                reply_markup=keyboard
            )
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
    else:
        await message.reply("⚠️ Отправьте текст или файл .txt.")

@router.callback_query(AssortmentConfirmState.waiting_for_confirm, F.data.startswith("assort_confirm:"))
async def process_assortment_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение или отмена загрузки ассортимента."""
    try:
        await callback.answer()
    except Exception as e:
        # Игнорируем, если не удалось ответить (telegram уже мог удалить кнопки)
        pass

    data = await state.get_data()
    categories = data.get("temp_categories")
    action = callback.data.split(":")[1]
    if action == "yes":
        if categories:
            await inventory.save_inventory(categories)
            await callback.message.edit_text("✅ Ассортимент успешно загружен и сохранён.")
        else:
            await callback.message.edit_text("❌ Ошибка: данные не найдены.")
    else:
        await callback.message.edit_text("❌ Загрузка отменена.")
    await state.clear()

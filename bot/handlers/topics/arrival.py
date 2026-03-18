import re
import tempfile
import os
import aiofiles
import logging
from aiogram import F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import config
from bot.repositories import ItemRepository
from bot.services.assortment import AssortmentService
from bot.handlers.states import ArrivalConfirmState
from bot.utils.validators import extract_serials

logger = logging.getLogger(__name__)

router = Router()
MAX_FILE_SIZE = 10 * 1024 * 1024

@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_ARRIVAL,
    (F.text | F.caption | F.document)
)
async def handle_arrival(message: Message, bot, state: FSMContext):
    current_state = await state.get_state()
    if current_state == ArrivalConfirmState.waiting_for_confirm.state:
        await message.reply("⚠️ Сначала подтвердите или отмените предыдущую загрузку (используйте кнопки).")
        return

    lines = []
    if message.document:
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
            lines = [line.strip() for line in content.splitlines() if line.strip()]
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
    else:
        content = message.text or message.caption
        if not content:
            await message.reply("⚠️ Отправьте текст, файл или фото с подписью.")
            return
        lines = [line.strip() for line in content.splitlines() if line.strip()]

    # Удаляем строки, состоящие только из дефисов
    lines = [line for line in lines if not re.match(r'^\s*-+\s*$', line)]
    if not lines:
        await message.reply("❌ Нет ни одной позиции после фильтрации.")
        return

    # Получаем существующие товары для проверки дубликатов
    existing_items = await ItemRepository.get_all_items_serials()
    existing_texts = {item['text'] for item in existing_items}
    existing_serials = {item['serial'] for item in existing_items if item['serial']}

    added_lines = []
    skipped_lines = []

    for line in lines:
        if line in existing_texts:
            skipped_lines.append(f"[Дубликат текста] {line}")
            continue
        serials = extract_serials(line)
        serial = serials[0] if serials else None
        if serial and serial in existing_serials:
            skipped_lines.append(f"[Дубликат серийного номера {serial}] {line}")
            continue
        added_lines.append(line)
        existing_texts.add(line)
        if serial:
            existing_serials.add(serial)

    if not added_lines:
        await message.reply("❌ Нет новых позиций для добавления (все дубликаты).")
        return

    await state.set_state(ArrivalConfirmState.waiting_for_confirm)
    await state.update_data(
        added_lines=added_lines,
        skipped_lines=skipped_lines,
        original_lines=lines,
        message_id=message.message_id,
        chat_id=message.chat.id,
        thread_id=message.message_thread_id
    )

    response = f"📦 Найдено новых позиций: {len(added_lines)}\n"
    if skipped_lines:
        response += f"⏭ Пропущено (дубликаты): {len(skipped_lines)}\n"
    response += "Подтвердите добавление?"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="arrival_confirm:yes"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="arrival_confirm:no")]
    ])
    await message.reply(response, reply_markup=keyboard)

@router.callback_query(ArrivalConfirmState.waiting_for_confirm, F.data.startswith("arrival_confirm:"))
async def process_arrival_confirm(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    data = await state.get_data()
    added_lines = data.get("added_lines")
    action = callback.data.split(":")[1]

    if action == "yes":
        if added_lines:
            # Добавляем товары
            for line in added_lines:
                serials = extract_serials(line)
                serial = serials[0] if serials else None
                await ItemRepository.add_item(text=line, serial=serial)
            AssortmentService.invalidate_cache()
            await callback.message.edit_text(f"✅ Добавлено {len(added_lines)} новых товаров.")
        else:
            await callback.message.edit_text("❌ Нет товаров для добавления.")
    elif action == "no":
        await callback.message.edit_text("❌ Добавление отменено.")
    else:
        await callback.message.edit_text("❌ Неизвестное действие.")
        logger.warning(f"Неизвестное действие в arrival_confirm: {action}")

    await state.clear()

@router.message(ArrivalConfirmState.waiting_for_confirm, F.text.lower() == "отмена")
async def cancel_arrival_confirm_by_text(message: Message, state: FSMContext):
    await state.clear()
    await message.reply("❌ Добавление отменено.")

@router.message(ArrivalConfirmState.waiting_for_confirm)
async def unexpected_message_in_arrival_confirm(message: Message, state: FSMContext):
    await message.reply("⚠️ Сначала подтвердите или отмените предыдущую загрузку (используйте кнопки или напишите 'отмена').")

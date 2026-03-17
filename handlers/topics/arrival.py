import re
import tempfile
import os
import aiofiles
from datetime import datetime
from aiogram import F, Router
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import config
import inventory
from database import get_all_items_serials, add_item
from sort_assortment import add_item_to_categories
from handlers.states import ArrivalConfirmState

router = Router()
MAX_FILE_SIZE = 10 * 1024 * 1024

# ✅ Добавлен фильтр: сообщение должно содержать текст, подпись или быть документом
@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_ARRIVAL,
    (F.text | F.caption | F.document)
)
async def handle_arrival(message: Message, bot, state: FSMContext):
    current_state = await state.get_state()
    if current_state == ArrivalConfirmState.waiting_for_confirm.state:
        await message.reply("⚠️ Сначала подтвердите или отмените предыдущую загрузку.")
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
            # Безопасность: если вдруг фильтр пропустил пустое сообщение
            await message.reply("⚠️ Отправьте текст, файл или фото с подписью.")
            return
        lines = [line.strip() for line in content.splitlines() if line.strip()]

    lines = [line for line in lines if not re.match(r'^\s*-+\s*$', line)]
    if not lines:
        await message.reply("❌ Нет ни одной позиции после фильтрации.")
        return

    existing_items = await get_all_items_serials()
    existing_texts = {item['text'] for item in existing_items}
    existing_serials = {item['serial'] for item in existing_items if item['serial']}

    added_lines = []
    skipped_lines = []

    for line in lines:
        if line in existing_texts:
            skipped_lines.append(f"[Дубликат текста] {line}")
            continue
        serial = inventory.extract_serial(line)
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

# Остальные хендлеры (callback, отмена) без изменений
@router.callback_query(ArrivalConfirmState.waiting_for_confirm, F.data.startswith("arrival_confirm:"))
async def process_arrival_confirm(callback: CallbackQuery, state: FSMContext):
    # ... (код без изменений)
    pass

@router.message(ArrivalConfirmState.waiting_for_confirm, F.text.lower() == "отмена")
async def cancel_arrival_confirm_by_text(message: Message, state: FSMContext):
    # ... (код без изменений)
    pass

@router.message(ArrivalConfirmState.waiting_for_confirm)
async def unexpected_message_in_arrival_confirm(message: Message, state: FSMContext):
    # ... (код без изменений)
    pass

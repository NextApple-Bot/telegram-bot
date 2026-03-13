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

@router.message(F.chat.id == config.MAIN_GROUP_ID, F.message_thread_id == config.THREAD_ARRIVAL)
async def handle_arrival(message: Message, bot, state: FSMContext):
    """Обрабатывает сообщение в топике Прибытие (добавление новых товаров)."""
    current_state = await state.get_state()
    if current_state == ArrivalConfirmState.waiting_for_confirm.state:
        await message.reply("⚠️ Сначала подтвердите или отмените предыдущую загрузку.")
        return

    lines = []
    if message.text:
        full_text = message.text.strip()
        if not full_text:
            await message.reply("❌ Пустой список.")
            return
        lines = [line.strip() for line in full_text.splitlines() if line.strip()]
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
            lines = [line.strip() for line in content.splitlines() if line.strip()]
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
    else:
        await message.reply("⚠️ Отправьте текст или файл .txt.")
        return

    # Фильтруем строки, состоящие только из дефисов
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

@router.callback_query(ArrivalConfirmState.waiting_for_confirm, F.data.startswith("arrival_confirm:"))
async def process_arrival_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение или отмена добавления товаров."""
    try:
        await callback.answer()
    except Exception:
        pass

    action = callback.data.split(":")[1]
    data = await state.get_data()
    added_lines = data.get("added_lines", [])
    skipped_lines = data.get("skipped_lines", [])

    if action == "yes":
        current_categories = await inventory.load_inventory()

        for line in added_lines:
            serial = inventory.extract_serial(line)
            updated_categories, idx = add_item_to_categories(line, current_categories)
            current_categories = updated_categories
            category_name = current_categories[idx]['header']
            await add_item(line, serial, category_name=category_name)

        combined_lines = []
        if added_lines:
            combined_lines.append(f"=== ДОБАВЛЕННЫЕ ({len(added_lines)}) ===")
            combined_lines.extend(added_lines)
            combined_lines.append("")
        if skipped_lines:
            combined_lines.append(f"=== ПРОПУЩЕННЫЕ ({len(skipped_lines)}) ===")
            combined_lines.extend(skipped_lines)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("\n".join(combined_lines))
            tmp_path = f.name

        today = datetime.now().strftime("%d.%m.%Y")
        filename = f"прибытие_{today}.txt"
        try:
            doc = FSInputFile(tmp_path, filename=filename)
            await callback.message.answer_document(
                doc,
                caption=f"✅ Добавлено: {len(added_lines)} | ⏭ Пропущено: {len(skipped_lines)}"
            )
        finally:
            os.unlink(tmp_path)

        await callback.message.edit_text("✅ Добавление подтверждено.")
    else:
        await callback.message.edit_text("❌ Добавление отменено.")

    await state.clear()

# Дополнительные обработчики для отмены через текст "отмена"
@router.message(ArrivalConfirmState.waiting_for_confirm, F.text.lower() == "отмена")
async def cancel_arrival_confirm_by_text(message: Message, state: FSMContext):
    data = await state.get_data()
    if message.chat.id == data.get("chat_id") and message.message_thread_id == data.get("thread_id"):
        await state.clear()
        await message.reply("❌ Добавление отменено.")

@router.message(ArrivalConfirmState.waiting_for_confirm)
async def unexpected_message_in_arrival_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    if message.chat.id == data.get("chat_id") and message.message_thread_id == data.get("thread_id"):
        await message.reply("⚠️ Сначала подтвердите или отмените предыдущую загрузку (используйте кнопки или напишите «отмена»).")

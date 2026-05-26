# bot/handlers/topics/arrival.py
# Полная версия с правильной работой с базой (get_async_session_factory)

import re
import os
import aiofiles
import logging
from aiogram import F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from sqlalchemy import text
from bot.db import get_async_session_factory

from bot import config
from bot.repositories import ItemRepository
from bot.services.assortment import AssortmentService
from bot.handlers.states import ArrivalConfirmState
from bot.utils.validators import extract_serials
from bot.utils.sort import extract_base_name, normalize_name
from bot.utils.helpers import send_and_clean

logger = logging.getLogger(__name__)
router = Router()

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


async def determine_category_for_item(item_text: str, categories: list) -> str:
    """Определяет категорию для товара"""
    stripped = item_text.strip()
    
    if stripped.startswith("Б/У -") or stripped.startswith("Б/У "):
        return "Б/У:"
    if stripped.startswith("NS -") or stripped.startswith("NS "):
        return "NS:"

    base = extract_base_name(item_text).lower()
    best_match = None
    best_len = 0

    for cat in categories:
        cat_header = cat.get('header', '')
        cat_name = normalize_name(cat_header).lower().rstrip(':')
        if not cat_name:
            continue
            
        if base.startswith(cat_name):
            remainder = base[len(cat_name):]
            if not remainder or remainder[0] == ' ':
                if len(cat_name) > best_len:
                    best_len = len(cat_name)
                    best_match = cat_header
        elif cat_name in base:
            if len(cat_name) > best_len:
                best_len = len(cat_name)
                best_match = cat_header

    if best_match:
        return best_match

    # Fallback для новых категорий
    if 'iphone' in item_text.lower():
        return extract_base_name(item_text) + ":"
    elif ',' in item_text:
        return item_text.split(',')[0].strip() + ":"
    else:
        words = item_text.split()[:3]
        return " ".join(words).strip() + ":"


@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_ARRIVAL,
    (F.text | F.caption | F.document)
)
async def handle_arrival(message: Message, bot, state: FSMContext):
    current_state = await state.get_state()
    if current_state == ArrivalConfirmState.waiting_for_confirm.state:
        await send_and_clean(
            bot=message.bot, chat_id=message.chat.id,
            text="⚠️ Сначала подтверди или отмени предыдущую загрузку (кнопки).",
            reply_to_message_id=message.message_id,
            message_thread_id=config.THREAD_ARRIVAL, delete_after=60
        )
        return

    # ... (логика чтения сообщения/файла остаётся той же)
    lines = []
    if message.document:
        # обработка документа
        document = message.document
        if document.file_size > MAX_FILE_SIZE:
            await send_and_clean(bot=message.bot, chat_id=message.chat.id,
                text="❌ Файл слишком большой (макс 10 МБ).",
                reply_to_message_id=message.message_id, message_thread_id=config.THREAD_ARRIVAL, delete_after=60)
            return
        if not (document.mime_type == 'text/plain' or document.file_name.endswith('.txt')):
            await send_and_clean(bot=message.bot, chat_id=message.chat.id,
                text="⚠️ Нужно отправить .txt файл", reply_to_message_id=message.message_id,
                message_thread_id=config.THREAD_ARRIVAL, delete_after=60)
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
        content = message.text or message.caption or ""
        lines = [line.strip() for line in content.splitlines() if line.strip()]

    lines = [line for line in lines if not re.match(r'^\s*-+\s*$', line)]

    # Склеивание серийника
    merged_lines, i = [], 0
    while i < len(lines):
        line = lines[i]
        if not extract_serials(line) and i + 1 < len(lines) and extract_serials(lines[i + 1]):
            merged_lines.append(f"{line} {lines[i + 1]}")
            i += 2
        else:
            merged_lines.append(line)
            i += 1
    lines = merged_lines

    filtered_lines = [line for line in lines if extract_serials(line)]
    skipped_no_serial = [line for line in lines if not extract_serials(line)]

    if not filtered_lines:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id,
            text="❌ Не найдено ни одной строки с серийным номером.", 
            reply_to_message_id=message.message_id, message_thread_id=config.THREAD_ARRIVAL, delete_after=60)
        return

    # Проверка дубликатов
    existing_items = await ItemRepository.get_all_items_serials()
    existing_texts = {item['text'] for item in existing_items}
    existing_serials = {item.get('serial', '').strip().upper() for item in existing_items if item.get('serial')}

    current_categories = await AssortmentService.load_inventory()
    cat_to_items = {}
    skipped_duplicates = []

    for line in filtered_lines:
        if line in existing_texts:
            skipped_duplicates.append(f"[Дубликат] {line}")
            continue
        serials = extract_serials(line)
        serial = serials[0].strip().upper()
        if serial in existing_serials:
            skipped_duplicates.append(f"[Дубликат серийника {serial}] {line}")
            continue

        category_name = await determine_category_for_item(line, current_categories)
        cat_to_items.setdefault(category_name, []).append((line, serial))

    if not cat_to_items:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id,
            text="❌ Все позиции уже существуют.", reply_to_message_id=message.message_id,
            message_thread_id=config.THREAD_ARRIVAL, delete_after=60)
        return

    # Сохраняем в FSM
    await state.set_state(ArrivalConfirmState.waiting_for_confirm)
    await state.update_data(cat_to_items=cat_to_items, skipped_duplicates=skipped_duplicates,
                            skipped_no_serial=skipped_no_serial)

    total_new = sum(len(items) for items in cat_to_items.values())
    text = f"📦 Найдено **{total_new}** новых товаров.\n"
    if skipped_no_serial:
        text += f"⚠️ Пропущено без серийника: {len(skipped_no_serial)}\n"
    if skipped_duplicates:
        text += f"⏭ Пропущено дубликатов: {len(skipped_duplicates)}\n"
    text += "\nПодтвердить добавление в базу?"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="arrival_confirm:yes"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="arrival_confirm:no")
    ]])

    await message.reply(text, reply_markup=keyboard)


@router.callback_query(ArrivalConfirmState.waiting_for_confirm, F.data.startswith("arrival_confirm:"))
async def process_arrival_confirm(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except:
        pass

    data = await state.get_data()
    cat_to_items = data.get("cat_to_items", {})
    action = callback.data.split(":")[1]

    if action == "yes" and cat_to_items:
        total_inserted = 0
        errors = []
        session_factory = get_async_session_factory()

        async with session_factory() as session:
            async with session.begin():
                for cat_name, items in cat_to_items.items():
                    cat_id = await ItemRepository.get_or_create_category(cat_name)
                    for text_line, serial in items:
                        is_booked = 'Бронь от' in text_line
                        try:
                            await session.execute(text("""
                                INSERT INTO items (text, serial, category_id, is_booked, created_at)
                                VALUES (:text, :serial, :category_id, :is_booked, NOW())
                            """), {
                                "text": text_line,
                                "serial": serial,
                                "category_id": cat_id,
                                "is_booked": is_booked
                            })
                            total_inserted += 1
                        except Exception as e:
                            logger.error(f"Ошибка вставки: {e}")
                            errors.append(str(e))

        await AssortmentService.invalidate_cache()
        await callback.message.edit_text(
            f"✅ Успешно добавлено **{total_inserted}** товаров.\n"
            f"Ошибок: {len(errors)}"
        )

    elif action == "no":
        await callback.message.edit_text("❌ Добавление отменено.")
    else:
        await callback.message.edit_text("❌ Нет данных для добавления.")

    await state.clear()

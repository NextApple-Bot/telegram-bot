# Файл: bot/handlers/topics/arrival.py
import re
import tempfile
import os
import aiofiles
import logging
from aiogram import F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from bot import config
from bot.repositories import ItemRepository
from bot.services.assortment import AssortmentService
from bot.handlers.states import ArrivalConfirmState
from bot.utils.validators import extract_serials
from bot.utils.sort import extract_base_name, normalize_name
from bot.db import get_pool
from bot.utils.helpers import send_and_clean

logger = logging.getLogger(__name__)

router = Router()
MAX_FILE_SIZE = 10 * 1024 * 1024


async def determine_category_for_item(item_text: str, categories: list) -> str:
    stripped = item_text.strip()
    if stripped.startswith("Б/У -") or stripped.startswith("Б/У "):
        return "Б/У:"
    if stripped.startswith("NS -") or stripped.startswith("NS "):
        return "NS:"

    base = extract_base_name(item_text).lower()
    best_match = None
    best_len = 0

    for cat in categories:
        cat_name = normalize_name(cat['header']).lower().rstrip(':')
        if not cat_name:
            continue

        if base.startswith(cat_name):
            remainder = base[len(cat_name):]
            # Исправлено: объединены условия if
            if (remainder == '' or remainder[0] == ' ') and len(cat_name) > best_len:
                best_len = len(cat_name)
                best_match = cat['header']
        elif cat_name in base:
            if len(cat_name) > best_len:
                best_len = len(cat_name)
                best_match = cat['header']

    if best_match:
        return best_match

    if 'iphone' in item_text.lower():
        base = extract_base_name(item_text)
        return f"{base}:"
    else:
        if ',' in item_text:
            new_header = item_text.split(',')[0].strip() + ':'
        else:
            words = item_text.split()
            new_header = ' '.join(words[:2]).strip() + ':'
        return normalize_name(new_header)


@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_ARRIVAL,
    (F.text | F.caption | F.document)
)
async def handle_arrival(message: Message, bot, state: FSMContext):
    current_state = await state.get_state()
    if current_state == ArrivalConfirmState.waiting_for_confirm.state:
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text="⚠️ Сначала подтвердите или отмените предыдущую загрузку (используйте кнопки).",
            reply_to_message_id=message.message_id,
            message_thread_id=config.THREAD_ARRIVAL,
            delete_after=60
        )
        return

    lines = []
    if message.document:
        document = message.document
        if document.file_size > MAX_FILE_SIZE:
            await send_and_clean(
                bot=message.bot,
                chat_id=message.chat.id,
                text="❌ Файл слишком большой (макс. 10 МБ).",
                reply_to_message_id=message.message_id,
                message_thread_id=config.THREAD_ARRIVAL,
                delete_after=60
            )
            return
        if not (document.mime_type == 'text/plain' or document.file_name.endswith('.txt')):
            await send_and_clean(
                bot=message.bot,
                chat_id=message.chat.id,
                text="⚠️ Отправьте текстовый файл .txt",
                reply_to_message_id=message.message_id,
                message_thread_id=config.THREAD_ARRIVAL,
                delete_after=60
            )
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
            await send_and_clean(
                bot=message.bot,
                chat_id=message.chat.id,
                text="⚠️ Отправьте текст, файл или фото с подписью.",
                reply_to_message_id=message.message_id,
                message_thread_id=config.THREAD_ARRIVAL,
                delete_after=60
            )
            return
        lines = [line.strip() for line in content.splitlines() if line.strip()]

    # Убираем строки-разделители (полностью из тире)
    lines = [line for line in lines if not re.match(r'^\s*-+\s*$', line)]

    # --- Склеиваем строки, где серийник на следующей строке (но не заголовки категорий) ---
    merged_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if (not extract_serials(line) and
            not line.strip().endswith(':') and
            i + 1 < len(lines) and
            extract_serials(lines[i + 1])):
            merged = f"{line} {lines[i + 1]}"
            merged_lines.append(merged)
            i += 2
        else:
            merged_lines.append(line)
            i += 1
    lines = merged_lines
    # ----------------------------------------------------------------

    filtered_lines = []
    skipped_no_serial = []
    for line in lines:
        serials = extract_serials(line)
        if serials:
            filtered_lines.append(line)
        else:
            skipped_no_serial.append(line)
            logger.info(f"Пропущена строка без серийного номера: {line}")

    if not filtered_lines:
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text="❌ Нет ни одной строки с серийным номером. Добавление отменено.",
            reply_to_message_id=message.message_id,
            message_thread_id=config.THREAD_ARRIVAL,
            delete_after=60
        )
        return

    existing_items = await ItemRepository.get_all_items_serials()
    existing_texts = {item['text'] for item in existing_items}
    existing_serials = {item['serial'].strip().upper() for item in existing_items if item['serial']}

    logger.info(f"Загружено существующих товаров: {len(existing_texts)} текстов, {len(existing_serials)} серийников")

    current_categories = await AssortmentService.load_inventory()

    cat_to_items = {}
    skipped_duplicates = []

    for line in filtered_lines:
        if line in existing_texts:
            skipped_duplicates.append(f"[Дубликат текста] {line}")
            logger.info(f"Дубликат по тексту: {line}")
            continue

        serials = extract_serials(line)
        if not serials:
            continue
        serial = serials[0].strip().upper() if serials else None
        if serial and serial in existing_serials:
            skipped_duplicates.append(f"[Дубликат серийного номера {serial}] {line}")
            logger.info(f"Дубликат по серийному номеру {serial}: {line}")
            continue

        category_name = await determine_category_for_item(line, current_categories)
        cat_to_items.setdefault(category_name, []).append((line, serial))

    if not cat_to_items:
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text="❌ Нет новых позиций для добавления (все дубликаты).",
            reply_to_message_id=message.message_id,
            message_thread_id=config.THREAD_ARRIVAL,
            delete_after=60
        )
        return

    await state.set_state(ArrivalConfirmState.waiting_for_confirm)
    await state.update_data(
        cat_to_items=cat_to_items,
        skipped_lines=skipped_duplicates,
        skipped_no_serial=skipped_no_serial,
        message_id=message.message_id,
        chat_id=message.chat.id,
        thread_id=message.message_thread_id
    )

    total_new = sum(len(items) for items in cat_to_items.values())
    response = f"📦 Найдено новых позиций с серийными номерами: {total_new}\n"
    if skipped_no_serial:
        response += f"⚠️ Пропущено (нет серийного номера): {len(skipped_no_serial)}\n"
    if skipped_duplicates:
        response += f"⏭ Пропущено (дубликаты): {len(skipped_duplicates)}\n"
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
    cat_to_items = data.get("cat_to_items")
    action = callback.data.split(":")[1]

    if action == "yes" and cat_to_items:
        pool = await get_pool()
        total_inserted = 0
        errors = []
        for cat_name, items in cat_to_items.items():
            cat_id = await ItemRepository.get_or_create_category(cat_name)
            for text, serial in items:
                is_booked = 'Бронь от' in text
                try:
                    async with pool.acquire() as conn:
                        await conn.execute('''
                            INSERT INTO items (text, serial, category_id, is_booked)
                            VALUES ($1, $2, $3, $4)
                        ''', text, serial, cat_id, is_booked)
                    total_inserted += 1
                except Exception as e:
                    error_msg = f"Ошибка при вставке товара {text}: {e}"
                    logger.exception(error_msg)
                    errors.append(error_msg)

        await AssortmentService.invalidate_cache()
        await callback.message.edit_text(f"✅ Добавлено {total_inserted} новых товаров. Ошибок: {len(errors)}")
        if errors:
            await send_and_clean(
                bot=callback.bot,
                chat_id=callback.message.chat.id,
                text="\n".join(errors[:5]),
                message_thread_id=config.THREAD_ARRIVAL,
                delete_after=60
            )
    elif action == "no":
        await callback.message.edit_text("❌ Добавление отменено.")
    else:
        await callback.message.edit_text("❌ Нет товаров для добавления.")

    await state.clear()


@router.message(ArrivalConfirmState.waiting_for_confirm, F.text.lower() == "отмена")
async def cancel_arrival_confirm_by_text(message: Message, state: FSMContext):
    await state.clear()
    await send_and_clean(
        bot=message.bot,
        chat_id=message.chat.id,
        text="❌ Добавление отменено.",
        reply_to_message_id=message.message_id,
        message_thread_id=config.THREAD_ARRIVAL,
        delete_after=60
    )


@router.message(ArrivalConfirmState.waiting_for_confirm)
async def unexpected_message_in_arrival_confirm(message: Message, state: FSMContext):
    await send_and_clean(
        bot=message.bot,
        chat_id=message.chat.id,
        text="⚠️ Сначала подтвердите или отмените предыдущую загрузку (используйте кнопки или напишите 'отмена').",
        reply_to_message_id=message.message_id,
        message_thread_id=config.THREAD_ARRIVAL,
        delete_after=60
    )

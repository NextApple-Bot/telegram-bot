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

logger = logging.getLogger(__name__)

router = Router()
MAX_FILE_SIZE = 10 * 1024 * 1024

async def determine_category_for_item(item_text: str, categories: list) -> str:
    """
    Определяет имя категории для товара на основе текущего списка категорий.
    Возвращает имя категории (с двоеточием в конце).
    """
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
            if remainder == '' or remainder[0] == ' ':
                if len(cat_name) > best_len:
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

def is_likely_item(line: str) -> bool:
    """
    Проверяет, похожа ли строка на товар.
    """
    stripped = line.strip()
    if extract_serials(line):
        return True
    if stripped.startswith('Б/У') or stripped.startswith('NS'):
        return True
    if '(' in line and ')' in line and re.search(r'\d', line):
        return True
    return False

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

    # Фильтруем строки, которые не похожи на товары
    filtered_lines = []
    skipped_not_item = []
    for line in lines:
        if is_likely_item(line):
            filtered_lines.append(line)
        else:
            skipped_not_item.append(line)

    if not filtered_lines:
        await message.reply("❌ Нет ни одной позиции, похожей на товар (все строки пропущены).")
        if skipped_not_item:
            logger.info(f"Пропущены строки, не похожие на товары: {skipped_not_item}")
        return

    # ОДИН РАЗ загружаем существующие товары из БД (текст и серийники)
    existing_items = await ItemRepository.get_all_items_serials()
    # Для быстрого поиска по тексту
    existing_texts = {item['text'] for item in existing_items}
    # Для быстрого поиска по серийному номеру (регистронезависимо)
    existing_serials = {item['serial'].strip().upper() for item in existing_items if item['serial']}
    
    logger.info(f"Загружено существующих товаров: {len(existing_texts)} текстов, {len(existing_serials)} серийников")

    # Загружаем текущие категории
    current_categories = await AssortmentService.load_inventory()

    cat_to_items = {}
    skipped_duplicates = []

    for line in filtered_lines:
        # Проверка дубликата по тексту
        if line in existing_texts:
            skipped_duplicates.append(f"[Дубликат текста] {line}")
            logger.info(f"Дубликат по тексту: {line}")
            continue

        serials = extract_serials(line)
        serial = serials[0].strip().upper() if serials else None
        if serial and serial in existing_serials:
            skipped_duplicates.append(f"[Дубликат серийного номера {serial}] {line}")
            logger.info(f"Дубликат по серийному номеру {serial}: {line}")
            continue

        category_name = await determine_category_for_item(line, current_categories)
        cat_to_items.setdefault(category_name, []).append((line, serial))

    if not cat_to_items:
        await message.reply("❌ Нет новых позиций для добавления (все дубликаты).")
        return

    await state.set_state(ArrivalConfirmState.waiting_for_confirm)
    await state.update_data(
        cat_to_items=cat_to_items,
        skipped_lines=skipped_duplicates,
        skipped_not_item=skipped_not_item,
        message_id=message.message_id,
        chat_id=message.chat.id,
        thread_id=message.message_thread_id
    )

    total_new = sum(len(items) for items in cat_to_items.values())
    response = f"📦 Найдено новых позиций: {total_new}\n"
    if skipped_not_item:
        response += f"⚠️ Пропущено (не похожи на товары): {len(skipped_not_item)}\n"
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
        async with pool.acquire() as conn:
            async with conn.transaction():
                cat_ids = {}
                for cat_name in cat_to_items.keys():
                    cat_id = await ItemRepository.get_or_create_category(cat_name)
                    cat_ids[cat_name] = cat_id

                all_rows = []
                for cat_name, items in cat_to_items.items():
                    cat_id = cat_ids[cat_name]
                    for text, serial in items:
                        is_booked = 'Бронь от' in text
                        all_rows.append((text, serial, cat_id, is_booked))

                if all_rows:
                    values_placeholder = []
                    params = []
                    idx = 1
                    for text, serial, cat_id, is_booked in all_rows:
                        values_placeholder.append(f"(${idx}, ${idx+1}, ${idx+2}, ${idx+3})")
                        params.extend([text, serial, cat_id, is_booked])
                        idx += 4
                    query = f'INSERT INTO items (text, serial, category_id, is_booked) VALUES {", ".join(values_placeholder)}'
                    await conn.execute(query, *params)

        AssortmentService.invalidate_cache()
        total_new = sum(len(items) for items in cat_to_items.values())
        await callback.message.edit_text(f"✅ Добавлено {total_new} новых товаров.")
    elif action == "no":
        await callback.message.edit_text("❌ Добавление отменено.")
    else:
        await callback.message.edit_text("❌ Нет товаров для добавления.")

    await state.clear()

@router.message(ArrivalConfirmState.waiting_for_confirm, F.text.lower() == "отмена")
async def cancel_arrival_confirm_by_text(message: Message, state: FSMContext):
    await state.clear()
    await message.reply("❌ Добавление отменено.")

@router.message(ArrivalConfirmState.waiting_for_confirm)
async def unexpected_message_in_arrival_confirm(message: Message, state: FSMContext):
    await message.reply("⚠️ Сначала подтвердите или отмените предыдущую загрузку (используйте кнопки или напишите 'отмена').")

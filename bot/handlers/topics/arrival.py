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
from bot.utils.sort import (
    find_category_for_item,
    extract_base_name,
    normalize_name,
    get_full_model_name
)

logger = logging.getLogger(__name__)

router = Router()
MAX_FILE_SIZE = 10 * 1024 * 1024

# Словарь известных брендов и соответствующих им названий категорий (без двоеточия)
BRAND_MAPPING = {
    'dyson': 'Dyson',
    'iphone': None,  # для iPhone особая логика
    'airpods': 'AirPods',
    'apple watch': 'Apple Watch',
    'samsung': 'Samsung',
    'xiaomi': 'Xiaomi',
    'huawei': 'Huawei',
}

async def determine_category_for_item(item_text: str, categories: list) -> str:
    """
    Определяет имя категории для товара на основе текущего списка категорий.
    Возвращает строку с двоеточием в конце.
    """
    # 1. Сначала пробуем найти категорию через find_category_for_item
    idx = find_category_for_item(item_text, categories)
    if idx is not None:
        return categories[idx]['header']

    # 2. Если не найдено, пробуем определить бренд
    lower_text = item_text.lower()
    for brand, cat_name in BRAND_MAPPING.items():
        if brand in lower_text:
            # Ищем существующую категорию по имени бренда
            for cat in categories:
                cat_name_lower = normalize_name(cat['header']).lower().rstrip(':')
                if cat_name_lower == brand or (cat_name and cat_name_lower == cat_name.lower()):
                    return cat['header']
            # Если категория для бренда не существует, создаём её
            if cat_name:
                return f"{cat_name}:"
            else:
                # Для iPhone используем extract_base_name
                base = extract_base_name(item_text)
                return f"{base}:"

    # 3. Если бренд не определён, используем стандартную логику
    if item_text.strip().startswith("Б/У -") or item_text.strip().startswith("Б/У "):
        return "Б/У:"

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

    # Загружаем текущие категории для определения подходящей
    current_categories = await AssortmentService.load_inventory()

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

        category_name = await determine_category_for_item(line, current_categories)
        added_lines.append((line, serial, category_name))
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
    logger.info(f"Получен callback с данными: {callback.data}")
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    data = await state.get_data()
    added_lines = data.get("added_lines")
    action = callback.data.split(":")[1]

    if action == "yes":
        if added_lines:
            for line, serial, category_name in added_lines:
                cat_id = await ItemRepository.get_or_create_category(category_name)
                await ItemRepository.add_item(text=line, serial=serial, category_id=cat_id)
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

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
from bot.utils.sort import find_category_for_item, extract_base_name, normalize_name

logger = logging.getLogger(__name__)

router = Router()
MAX_FILE_SIZE = 10 * 1024 * 1024

# Словарь известных брендов и соответствующих им названий категорий
BRAND_CATEGORIES = {
    'dyson': 'Dyson:',
    'iphone': None,  # для iPhone особая логика в extract_base_name, но здесь можно оставить
    'airpods': 'AirPods:',
    'apple watch': 'Apple Watch:',
    'samsung': 'Samsung:',
    'xiaomi': 'Xiaomi:',
    'huawei': 'Huawei:',
}

async def determine_category_for_item(item_text: str, categories: list) -> str:
    """
    Определяет имя категории для товара на основе текущего списка категорий.
    Сначала пытается найти существующую категорию через find_category_for_item.
    Если не находит, проверяет наличие известных брендов и ищет соответствующую категорию.
    В противном случае создаёт новую категорию по правилам из sort.py.
    """
    # 1. Пытаемся найти по точному совпадению через find_category_for_item
    idx = find_category_for_item(item_text, categories)
    if idx is not None:
        return categories[idx]['header']

    # 2. Если не найдено, пробуем определить бренд
    lower_text = item_text.lower()
    for brand, cat_name in BRAND_CATEGORIES.items():
        if brand in lower_text:
            # Проверяем, есть ли уже категория с таким названием
            for cat in categories:
                if normalize_name(cat['header']).lower().rstrip(':') == brand:
                    return cat['header']
            # Если нет, возвращаем стандартное название для этого бренда
            if cat_name:
                return cat_name
            else:
                # Для iPhone используем extract_base_name
                if brand == 'iphone':
                    base = extract_base_name(item_text)
                    return f"{base}:"

    # 3. Если бренд не определён, используем старую логику создания новой категории
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
    # ... (код без изменений, такой же как в предыдущем ответе, но с новой функцией выше)
    # (полный код см. в предыдущем ответе, здесь он не дублируется для краткости)
    pass

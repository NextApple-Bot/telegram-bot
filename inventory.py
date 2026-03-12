import re
from database import (
    add_item, remove_item_by_serial, get_all_categories_with_items,
    get_or_create_category, update_category_items
)

def extract_serial(line):
    """
    Извлекает серийный номер из строки товара.
    - Если в скобках есть символ '№', возвращает всё содержимое скобок.
    - Иначе ищет комбинацию букв и цифр (длиной от 5 символов) или длинное число (≥10 цифр).
    Возвращает нормализованный серийный номер (верхний регистр, обрезанный) или None.
    """
    matches = re.finditer(r'\(([^)]+)\)', line)  # всё, что в скобках
    for match in matches:
        candidate = match.group(1).strip()
        # Если есть символ №, считаем это серийным номером
        if '№' in candidate:
            return candidate.upper()
        # Проверяем на наличие букв и цифр
        if re.search(r'[A-Za-z]', candidate) and re.search(r'[0-9]', candidate):
            if len(candidate) >= 5:
                return candidate.upper()
        # Если это длинное число (например, IMEI)
        if candidate.isdigit() and len(candidate) >= 10:
            return candidate
    return None

def extract_serials_from_text(text):
    """
    Извлекает все серийные номера из текста сообщения (для продаж).
    Работает аналогично extract_serial, но возвращает список.
    """
    serials = set()
    matches = re.finditer(r'\(([^)]+)\)', text)
    for match in matches:
        candidate = match.group(1).strip()
        if '№' in candidate:
            serials.add(candidate.upper())
        elif re.search(r'[A-Za-z]', candidate) and re.search(r'[0-9]', candidate):
            if len(candidate) >= 5:
                serials.add(candidate.upper())
        elif candidate.isdigit() and len(candidate) >= 10:
            serials.add(candidate)
    return list(serials)

async def load_inventory():
    """Возвращает список ВСЕХ категорий с товарами (включая пустые)."""
    categories = await get_all_categories_with_items()
    return categories

async def save_inventory(categories):
    """
    Обновляет ассортимент, сохраняя все существующие категории.
    - Категории, указанные в categories, обновляются (старые товары заменяются новыми).
    - Категории, не указанные, остаются без изменений (вместе со своими товарами).
    - Новые категории создаются.
    """
    for cat in categories:
        cat_name = cat['header']
        items = cat['items']
        await update_category_items(cat_name, items)

async def remove_by_serial(serial: str) -> int:
    """Удаляет товар по серийному номеру."""
    return await remove_item_by_serial(serial)

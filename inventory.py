import time
from database import (
    add_item, remove_item_by_serial, get_all_categories_with_items,
    get_or_create_category, update_category_items, clear_all_inventory
)
from serial_utils import extract_serial, extract_serials_from_text

# Кеш для ассортимента
_cache = {"data": None, "timestamp": 0}
CACHE_TTL = 10  # время жизни кеша в секундах

def invalidate_cache():
    """Сбрасывает кеш ассортимента."""
    global _cache
    _cache["data"] = None
    _cache["timestamp"] = 0

async def load_inventory():
    """Возвращает список ВСЕХ категорий с товарами (включая пустые) с использованием кеша."""
    global _cache
    now = time.time()
    if _cache["data"] is not None and (now - _cache["timestamp"]) < CACHE_TTL:
        return _cache["data"]
    # Кеш устарел или пуст – загружаем из БД
    categories = await get_all_categories_with_items()
    _cache["data"] = categories
    _cache["timestamp"] = now
    return categories

async def save_inventory(categories):
    """Обновляет ассортимент. Если передан пустой список, полностью очищает его."""
    if not categories:
        await clear_all_inventory()
        invalidate_cache()
        return
    for cat in categories:
        cat_name = cat['header']
        items = cat['items']
        await update_category_items(cat_name, items)
    invalidate_cache()

async def remove_by_serial(serial: str) -> int:
    """Удаляет товар по серийному номеру."""
    result = await remove_item_by_serial(serial)
    invalidate_cache()
    return result

import time
from database import (
    add_item, remove_item_by_serial, get_all_categories_with_items,
    get_or_create_category, update_category_items, clear_all_inventory,
    get_item_by_serial, add_deleted_item
)
from serial_utils import extract_serials

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

def extract_serial(line: str) -> str | None:
    """Извлекает первый серийный номер из строки."""
    serials = extract_serials(line)
    return serials[0] if serials else None

async def remove_by_serial(serial: str, reason: str = 'manual') -> int:
    """
    Удаляет товар по серийному номеру и сохраняет в историю удалений.
    Возвращает количество удалённых записей (0 или 1).
    """
    # Получаем данные товара до удаления
    item = await get_item_by_serial(serial)
    if not item:
        return 0

    # 1. Сначала сохраняем в deleted_items (пока запись ещё существует)
    await add_deleted_item(
        item_id=item['id'],
        text=item['text'],
        serial=serial,
        category_id=item['category_id'],
        reason=reason
    )

    # 2. Затем удаляем сам товар
    removed_count = await remove_item_by_serial(serial)
    if removed_count > 0:
        invalidate_cache()
        return removed_count
    else:
        # Если удаление не удалось (маловероятно), запись в deleted_items останется как артефакт
        logger.warning(f"Товар {serial} сохранён в deleted_items, но не был удалён из items")
        return 0

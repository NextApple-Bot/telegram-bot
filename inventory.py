from database import (
    add_item, remove_item_by_serial, get_all_categories_with_items,
    get_or_create_category, update_category_items, clear_all_inventory
)
from serial_utils import extract_serial, extract_serials_from_text

async def load_inventory():
    """Возвращает список ВСЕХ категорий с товарами (включая пустые)."""
    categories = await get_all_categories_with_items()
    return categories

async def save_inventory(categories):
    """Обновляет ассортимент. Если передан пустой список, полностью очищает его."""
    if not categories:
        await clear_all_inventory()
        return

    for cat in categories:
        cat_name = cat['header']
        items = cat['items']
        await update_category_items(cat_name, items)

async def remove_by_serial(serial: str) -> int:
    """Удаляет товар по серийному номеру."""
    return await remove_item_by_serial(serial)

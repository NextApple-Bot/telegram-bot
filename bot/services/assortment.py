import logging
from bot.repositories import ItemRepository
from bot.utils.validators import extract_serials

logger = logging.getLogger(__name__)

class AssortmentService:
    _cache = {"data": None, "timestamp": 0}
    CACHE_TTL = 10

    @classmethod
    def invalidate_cache(cls):
        cls._cache["data"] = None
        cls._cache["timestamp"] = 0

    @classmethod
    async def load_inventory(cls):
        import time
        now = time.time()
        if cls._cache["data"] and (now - cls._cache["timestamp"]) < cls.CACHE_TTL:
            return cls._cache["data"]
        categories = await ItemRepository.get_all_categories_with_items()
        cls._cache["data"] = categories
        cls._cache["timestamp"] = now
        return categories

    @classmethod
    async def save_inventory(cls, categories: list):
        if not categories:
            await ItemRepository.clear_all_inventory()
            cls.invalidate_cache()
            return
        for cat in categories:
            cat_name = cat['header']
            items = cat['items']
            await ItemRepository.update_category_items(cat_name, items)
        cls.invalidate_cache()

    @classmethod
    async def remove_by_serial(cls, serial: str, reason: str = 'manual') -> int:
        """Удаляет товар по серийному номеру с сохранением в deleted_items (в транзакции)."""
        item = await ItemRepository.get_item_by_serial(serial)
        if not item:
            return 0

        # Транзакция вручную через pool
        from bot.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await ItemRepository.add_deleted_item(
                    item_id=item['id'],
                    text=item['text'],
                    serial=serial,
                    category_id=item['category_id'],
                    reason=reason
                )
                removed_count = await ItemRepository.remove_item_by_serial(serial)
        if removed_count > 0:
            cls.invalidate_cache()
        return removed_count

    @classmethod
    async def add_items(cls, lines: list):
        """Добавляет новые товары (используется в arrival)."""
        from bot.utils.sort import add_item_to_categories
        # Здесь можно реализовать добавление с проверкой дубликатов,
        # но в новом коде это делается в хендлере arrival с предварительной проверкой.
        # Для простоты оставим логику в хендлере.
        pass

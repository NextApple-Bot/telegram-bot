import logging
import asyncio
from bot.repositories import ItemRepository

logger = logging.getLogger(__name__)

class AssortmentService:
    _cache = {"data": None, "timestamp": 0}
    CACHE_TTL = 10
    _cache_lock = asyncio.Lock()  # Блокировка для защиты кеша

    @classmethod
    def invalidate_cache(cls):
        """Сбрасывает кеш ассортимента."""
        cls._cache["data"] = None
        cls._cache["timestamp"] = 0

    @classmethod
    async def load_inventory(cls):
        """
        Возвращает список всех категорий с товарами.
        Использует кеш с TTL для уменьшения нагрузки на БД.
        """
        import time
        now = time.time()
        
        # Быстрая проверка без блокировки
        if cls._cache["data"] and (now - cls._cache["timestamp"]) < cls.CACHE_TTL:
            return cls._cache["data"]
        
        # Если кеш устарел, блокируем и обновляем
        async with cls._cache_lock:
            # Double-checked locking
            if cls._cache["data"] and (now - cls._cache["timestamp"]) < cls.CACHE_TTL:
                return cls._cache["data"]
            
            categories = await ItemRepository.get_all_categories_with_items()
            cls._cache["data"] = categories
            cls._cache["timestamp"] = now
            return categories

    @classmethod
    async def save_inventory(cls, categories: list):
        """Сохраняет ассортимент (заменяет существующий)."""
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

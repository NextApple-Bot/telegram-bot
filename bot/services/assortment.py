# Файл: bot/services/assortment.py
import logging
import asyncio
from bot.repositories import ItemRepository

logger = logging.getLogger(__name__)

class AssortmentService:
    _cache = {"data": None, "timestamp": 0, "loading": False}
    CACHE_TTL = 10
    _cache_lock = asyncio.Lock()

    @classmethod
    def invalidate_cache(cls):
        """Сбрасывает кэш."""
        cls._cache["data"] = None
        cls._cache["timestamp"] = 0
        logger.debug("Кэш ассортимента инвалидирован")

    @classmethod
    async def load_inventory(cls):
        """Загружает ассортимент с кэшированием."""
        import time
        now = time.time()
        
        if cls._cache["data"] and (now - cls._cache["timestamp"]) < cls.CACHE_TTL:
            return cls._cache["data"]
        
        async with cls._cache_lock:
            if cls._cache["data"] and (now - cls._cache["timestamp"]) < cls.CACHE_TTL:
                return cls._cache["data"]
            
            categories = await ItemRepository.get_all_categories_with_items()
            cls._cache["data"] = categories
            cls._cache["timestamp"] = now
            return categories

    @classmethod
    async def save_inventory(cls, categories):
        """
        Сохраняет ассортимент (заменяет текущий). Ожидает список категорий в формате:
        [{"header": "Категория:", "items": ["товар1", "товар2"]}, ...]
        """
        await ItemRepository.bulk_replace_assortment(categories)
        cls.invalidate_cache()
        logger.info(f"Ассортимент сохранён: {len(categories)} категорий")

    @classmethod
    async def remove_by_serial(cls, serial: str, reason: str = 'manual', conn=None) -> int:
        """Удаляет товар по серийному номеру с сохранением в deleted_items."""
        item = await ItemRepository.get_item_by_serial(serial, conn=conn)
        if not item:
            return 0

        if conn is None:
            from bot.db import get_pool
            pool = await get_pool()
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await ItemRepository.add_deleted_item(
                        item_id=item['id'],
                        text=item['text'],
                        serial=serial,
                        category_id=item['category_id'],
                        reason=reason,
                        conn=conn
                    )
                    removed_count = await ItemRepository.remove_item_by_serial(serial, conn=conn)
        else:
            await ItemRepository.add_deleted_item(
                item_id=item['id'],
                text=item['text'],
                serial=serial,
                category_id=item['category_id'],
                reason=reason,
                conn=conn
            )
            removed_count = await ItemRepository.remove_item_by_serial(serial, conn=conn)

        if removed_count > 0:
            cls.invalidate_cache()
        return removed_count

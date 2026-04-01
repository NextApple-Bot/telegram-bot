import logging
import asyncio
from bot.repositories import ItemRepository

logger = logging.getLogger(__name__)

class AssortmentService:
    _cache = {"data": None, "timestamp": 0}
    CACHE_TTL = 10
    _cache_lock = asyncio.Lock()

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
        async with cls._cache_lock:
            if cls._cache["data"] and (now - cls._cache["timestamp"]) < cls.CACHE_TTL:
                return cls._cache["data"]
            categories = await ItemRepository.get_all_categories_with_items()
            cls._cache["data"] = categories
            cls._cache["timestamp"] = now
            return categories

    @classmethod
    async def remove_by_serial(cls, serial: str, reason: str = 'manual', conn=None) -> int:
        """Удаляет товар по серийному номеру с сохранением в deleted_items (в транзакции)."""
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
            # Уже в транзакции
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

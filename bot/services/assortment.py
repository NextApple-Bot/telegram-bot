# Файл: bot/services/assortment.py
import logging
from typing import List, Dict
from bot.repositories import ItemRepository
from bot.services.cache import RedisCache

logger = logging.getLogger(__name__)

CACHE_KEY_ASSORTMENT = "assortment:full"
CACHE_TTL = 300  # 5 минут

class AssortmentService:
    @classmethod
    async def load_inventory(cls) -> List[Dict]:
        """Загружает ассортимент с кэшированием в Redis."""
        # Пытаемся взять из кэша
        cached = await RedisCache.get(CACHE_KEY_ASSORTMENT)
        if cached is not None:
            logger.debug("Ассортимент загружен из Redis-кэша")
            return cached

        # Если нет в кэше – загружаем из БД
        categories = await ItemRepository.get_all_categories_with_items()
        await RedisCache.set(CACHE_KEY_ASSORTMENT, categories, ttl=CACHE_TTL)
        logger.info("Ассортимент загружен из БД и сохранён в Redis-кэш")
        return categories

    @classmethod
    async def invalidate_cache(cls) -> None:
        """Сбрасывает кэш ассортимента."""
        await RedisCache.delete(CACHE_KEY_ASSORTMENT)
        logger.debug("Кэш ассортимента инвалидирован")

    @classmethod
    async def save_inventory(cls, categories: List[Dict]) -> None:
        """Сохраняет ассортимент в БД и сбрасывает кэш."""
        await ItemRepository.bulk_replace_assortment(categories)
        await cls.invalidate_cache()
        logger.info(f"Ассортимент сохранён: {len(categories)} категорий")

    @classmethod
    async def remove_by_serial(cls, serial: str, reason: str = 'manual', conn=None) -> int:
        """Удаляет товар по серийному номеру, сбрасывает кэш."""
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
            await cls.invalidate_cache()
        return removed_count

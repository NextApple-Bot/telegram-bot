# Файл: bot/services/assortment.py
import logging

from bot.services.cache import cache

logger = logging.getLogger(__name__)

class AssortmentService:
    CACHE_KEY = "assortment:all"
    CACHE_TTL = 10  # секунд

    @classmethod
    async def invalidate_cache(cls):
        await cache.delete(cls.CACHE_KEY)
        logger.debug("Кэш ассортимента инвалидирован (Redis)")

    @classmethod
    async def load_inventory(cls) -> list[dict[str, list[str]]]:
        try:
            cached = await cache.get(cls.CACHE_KEY)
            if cached is not None:
                logger.debug("Ассортимент загружен из Redis-кэша")
                return cached
        except Exception as e:
            logger.error(f"Ошибка при чтении кэша ассортимента: {e}, извлекаем из БД")

        # Локальный импорт для избежания циклической зависимости
        from bot.repositories import ItemRepository
        categories = await ItemRepository.get_all_categories_with_items()
        try:
            await cache.set(cls.CACHE_KEY, categories, ttl=cls.CACHE_TTL)
            logger.debug("Ассортимент загружен из БД и сохранён в Redis-кэш")
        except Exception as e:
            logger.warning(f"Не удалось сохранить ассортимент в кэш: {e}")
        return categories

    @classmethod
    async def save_inventory(cls, categories: list[dict[str, list[str]]]):
        from bot.repositories import ItemRepository
        await ItemRepository.bulk_replace_assortment(categories)
        await cls.invalidate_cache()
        logger.info(f"Ассортимент сохранён: {len(categories)} категорий")

    @classmethod
    async def remove_by_serial(cls, serial: str, reason: str = 'manual', conn=None) -> int:
        from bot.db import get_pool

        normalized_serial = serial.strip().upper()
        if conn is None:
            pool = await get_pool()
            async with pool.acquire() as conn, conn.transaction():
                deleted_row = await conn.fetchrow(
                    """
                    DELETE FROM items
                    WHERE UPPER(serial) = $1
                    RETURNING id, text, category_id
                    """,
                    normalized_serial
                )
                if deleted_row:
                    try:
                        await conn.execute(
                            """
                            INSERT INTO deleted_items (item_id, text, serial, category_id, reason)
                            VALUES ($1, $2, $3, $4, $5)
                            """,
                            deleted_row['id'], deleted_row['text'], serial, deleted_row['category_id'], reason
                        )
                    except Exception as e:
                        logger.warning(f"Не удалось вставить в deleted_items для {serial}: {e}")
                    await cls.invalidate_cache()
                    return 1
                return 0
        else:
            async with conn.transaction():
                deleted_row = await conn.fetchrow(
                    """
                    DELETE FROM items
                    WHERE UPPER(serial) = $1
                    RETURNING id, text, category_id
                    """,
                    normalized_serial
                )
                if deleted_row:
                    try:
                        await conn.execute(
                            """
                            INSERT INTO deleted_items (item_id, text, serial, category_id, reason)
                            VALUES ($1, $2, $3, $4, $5)
                            """,
                            deleted_row['id'], deleted_row['text'], serial, deleted_row['category_id'], reason
                        )
                    except Exception as e:
                        logger.warning(f"Не удалось вставить в deleted_items для {serial}: {e}")
                    await cls.invalidate_cache()
                    return 1
                return 0

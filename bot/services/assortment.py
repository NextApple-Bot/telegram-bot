# Файл: bot/services/assortment.py
import logging
from typing import List, Dict
from bot.repositories import ItemRepository
from bot.services.cache import cache

logger = logging.getLogger(__name__)

class AssortmentService:
    CACHE_KEY = "assortment:all"
    CACHE_TTL = 10  # секунд

    @classmethod
    async def invalidate_cache(cls):
        """Сбрасывает кэш ассортимента в Redis."""
        await cache.delete(cls.CACHE_KEY)
        logger.debug("Кэш ассортимента инвалидирован (Redis)")

    @classmethod
    async def load_inventory(cls) -> List[Dict[str, List[str]]]:
        """Загружает ассортимент с кэшированием через Redis."""
        # Пытаемся взять из кэша
        cached = await cache.get(cls.CACHE_KEY)
        if cached:
            logger.debug("Ассортимент загружен из Redis-кэша")
            return cached
        
        # Загружаем из БД
        categories = await ItemRepository.get_all_categories_with_items()
        # Сохраняем в кэш
        await cache.set(cls.CACHE_KEY, categories, ttl=cls.CACHE_TTL)
        logger.debug("Ассортимент загружен из БД и сохранён в Redis-кэш")
        return categories

    @classmethod
    async def save_inventory(cls, categories: List[Dict[str, List[str]]]):
        """Сохраняет ассортимент (заменяет текущий)."""
        await ItemRepository.bulk_replace_assortment(categories)
        await cls.invalidate_cache()
        logger.info(f"Ассортимент сохранён: {len(categories)} категорий")

    @classmethod
    async def remove_by_serial(cls, serial: str, reason: str = 'manual', conn=None) -> int:
        """
        Удаляет товар по серийному номеру с сохранением в deleted_items.
        Используется атомарный DELETE ... RETURNING для избежания гонок.
        Добавлена защита от ошибок внешнего ключа.
        """
        from bot.db import get_pool
        
        normalized_serial = serial.strip().upper()
        if conn is None:
            pool = await get_pool()
            async with pool.acquire() as conn:
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
                        # Проверяем, что запись с таким item_id действительно была удалена (существует в момент транзакции)
                        # и вставляем в deleted_items с обработкой возможной ошибки внешнего ключа
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
                            # Всё равно считаем, что товар удалён, раз DELETE прошёл
                        await cls.invalidate_cache()
                        return 1
                    return 0
        else:
            # Используем переданное соединение
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

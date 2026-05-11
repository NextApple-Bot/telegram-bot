import logging

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from bot.db import get_async_session_factory
from bot.models import DeletedItem, Item
from bot.services.cache import cache
from bot.services.lock import redis_lock

logger = logging.getLogger(__name__)

class AssortmentService:
    CACHE_KEY = "assortment:all"
    CACHE_TTL = 10  # секунд (оставлено как есть)

    @classmethod
    async def invalidate_cache(cls):
        await cache.delete(cls.CACHE_KEY)
        logger.debug("Кэш ассортимента инвалидирован")

    @classmethod
    async def load_inventory(cls) -> list[dict[str, list[str]]]:
        try:
            cached = await cache.get(cls.CACHE_KEY)
            if cached is not None:
                return cached
        except Exception:
            pass

        from bot.repositories import ItemRepository
        categories = await ItemRepository.get_all_categories_with_items()
        try:
            await cache.set(cls.CACHE_KEY, categories, ttl=cls.CACHE_TTL)
        except Exception:
            pass
        return categories

    @classmethod
    async def save_inventory(cls, categories: list[dict[str, list[str]]]):
        from bot.repositories import ItemRepository
        await ItemRepository.bulk_replace_assortment(categories)
        await cls.invalidate_cache()

    @classmethod
    async def remove_by_serial(cls, serial: str, reason: str = 'manual', conn=None) -> int:
        """
        Удаляет товар по серийному номеру с блокировкой строки FOR UPDATE.
        Если conn передан, используется эта же сессия, иначе создаётся новая.
        """
        normalized = serial.strip().upper()
        if conn is not None:
            session = conn
            own = False
        else:
            async_session = get_async_session_factory()
            session = async_session()
            own = True
        try:
            if own:
                await session.begin()
            # Блокируем строку для обновления
            stmt = select(Item).where(func.upper(Item.serial) == normalized).with_for_update()
            item = (await session.execute(stmt)).scalar_one_or_none()
            if item:
                # Добавляем в архив
                session.add(DeletedItem(
                    item_id=item.id,
                    text=item.text,
                    serial=item.serial,
                    category_id=item.category_id,
                    reason=reason
                ))
                await session.delete(item)
                await cls.invalidate_cache()
                if own:
                    await session.commit()
                return 1
            if own:
                await session.commit()
            return 0
        except SQLAlchemyError as e:
            if own:
                await session.rollback()
            logger.error(f"Ошибка удаления по серийному номеру {serial}: {e}")
            return 0
        finally:
            if own:
                await session.close()

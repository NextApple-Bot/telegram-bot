import logging
from typing import List, Dict, Any

import pandas as pd
from sqlalchemy import select, delete, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import get_async_session_factory
from bot.models import Category, Item

logger = logging.getLogger(__name__)


class AssortmentService:
    """Сервис для работы с ассортиментом (категории + товары)."""

    @staticmethod
    async def load_inventory() -> List[Dict[str, Any]]:
        async with get_async_session_factory()() as session:
            query = (
                select(Category, Item)
                .outerjoin(Item, Category.id == Item.category_id)
                .order_by(Category.sort_order.nulls_last(), Item.text)
            )
            result = await session.execute(query)
            rows = result.all()

        categories: Dict[str, Dict[str, Any]] = {}
        for cat, item in rows:
            cat_name = cat.name.strip()
            if cat_name not in categories:
                categories[cat_name] = {
                    "id": cat.id,
                    "name": cat_name,
                    "sort_order": cat.sort_order,
                    "items": []
                }
            if item:
                categories[cat_name]["items"].append({
                    "id": item.id,
                    "text": item.text.strip(),
                    "serial": item.serial,
                    "is_booked": item.is_booked,
                })
        return list(categories.values())

    @staticmethod
    async def remove_by_serial(serial: str, reason: str = 'sale', conn=None) -> bool:
        """
        Удаляет товар по серийному номеру + сохраняет в deleted_items.
        Если передан conn — работает внутри существующей транзакции.
        """
        from bot.repositories import ItemRepository

        if not serial:
            return False

        normalized = serial.strip().upper()

        try:
            item = await ItemRepository.get_item_by_serial(normalized)
            if not item:
                logger.warning(f"[AssortmentService] Товар {normalized} не найден")
                return False

            if conn:
                deleted = await ItemRepository.remove_item_by_serial(normalized, conn=conn)
            else:
                deleted = await ItemRepository.remove_item_by_serial(normalized)

            if deleted == 0:
                return False

            await ItemRepository.add_deleted_item(
                item_id=item.get('id'),
                text=item.get('text', ''),
                serial=normalized,
                category_id=item.get('category_id'),
                reason=reason
            )

            if not conn:
                await AssortmentService.invalidate_cache()

            logger.info(f"[AssortmentService] Товар {normalized} удалён (причина: {reason})")
            return True

        except Exception as e:
            logger.exception(f"[AssortmentService] Ошибка при удалении товара {normalized}")
            return False

    @staticmethod
    async def invalidate_cache():
        from bot.services.cache import cache
        await cache.delete("assortment:all")

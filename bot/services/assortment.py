import logging
from typing import List, Dict, Any

import pandas as pd
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import get_async_session_factory
from bot.models import Category, Item

logger = logging.getLogger(__name__)


class AssortmentService:
    """Сервис для работы с ассортиментом (категории + товары)."""

    @staticmethod
    async def load_inventory() -> List[Dict[str, Any]]:
        """Загружает весь ассортимент с группировкой по категориям."""
        async with get_async_session_factory()() as session:
            query = (
                select(Category, Item)
                .outerjoin(Item, Category.id == Item.category_id)
                .order_by(Category.name, Item.text)
            )
            result = await session.execute(query)
            rows = result.all()

        # Группировка
        categories: Dict[str, Dict[str, Any]] = {}
        for cat, item in rows:
            cat_name = cat.name.strip()
            if cat_name not in categories:
                categories[cat_name] = {
                    "id": cat.id,
                    "name": cat_name,
                    "items": []
                }

            if item:
                categories[cat_name]["items"].append({
                    "id": item.id,
                    "text": item.text.strip(),
                    "price": item.price,
                    "is_booked": item.is_booked,
                    "booking_info": item.booking_info,
                    "serial": item.serial,
                })

        return list(categories.values())

    @staticmethod
    async def import_arrival_from_excel(file_path: str) -> Dict[str, Any]:
        """Импорт нового ассортимента из Excel-файла (прибытие)."""
        try:
            df = pd.read_excel(file_path)

            # Ожидаемые колонки: category, text, price (опционально)
            required_cols = ['category', 'text']
            if not all(col in df.columns for col in required_cols):
                return {
                    "success": False,
                    "error": f"Неверный формат файла. Нужны колонки: {required_cols}"
                }

            added_categories = 0
            added_items = 0
            updated_items = 0

            async with get_async_session_factory()() as session:
                for _, row in df.iterrows():
                    category_name = str(row['category']).strip()
                    item_text = str(row['text']).strip()
                    price = int(row['price']) if 'price' in row and pd.notna(row['price']) else None

                    if not category_name or not item_text:
                        continue

                    # Находим или создаём категорию
                    category = await session.scalar(
                        select(Category).where(Category.name.ilike(category_name))
                    )
                    if not category:
                        category = Category(name=category_name)
                        session.add(category)
                        await session.flush()
                        added_categories += 1

                    # Проверяем, есть ли уже такой товар
                    existing_item = await session.scalar(
                        select(Item).where(
                            Item.category_id == category.id,
                            Item.text.ilike(item_text)
                        )
                    )

                    if existing_item:
                        # Обновляем цену, если изменилась
                        if price is not None and existing_item.price != price:
                            existing_item.price = price
                            updated_items += 1
                    else:
                        # Добавляем новый товар
                        new_item = Item(
                            text=item_text,
                            category_id=category.id,
                            price=price,
                            is_booked=False
                        )
                        session.add(new_item)
                        added_items += 1

                await session.commit()

            return {
                "success": True,
                "added_categories": added_categories,
                "added_items": added_items,
                "updated_items": updated_items
            }

        except Exception as e:
            logger.exception("Ошибка импорта из Excel")
            return {"success": False, "error": str(e)}

    @staticmethod
    async def add_category(name: str) -> bool:
        """Добавляет новую категорию."""
        if not name or len(name.strip()) < 2:
            return False

        name = name.strip()
        async with get_async_session_factory()() as session:
            existing = await session.scalar(
                select(Category).where(Category.name.ilike(name))
            )
            if existing:
                return False

            category = Category(name=name)
            session.add(category)
            await session.commit()
            return True

    @staticmethod
    async def add_item(text: str, category_id: int, price: int | None = None) -> bool:
        """Добавляет товар в категорию."""
        if not text or not category_id:
            return False

        async with get_async_session_factory()() as session:
            category = await session.get(Category, category_id)
            if not category:
                return False

            item = Item(
                text=text.strip(),
                category_id=category_id,
                price=price,
                is_booked=False
            )
            session.add(item)
            await session.commit()
            return True

    @staticmethod
    async def delete_all_items() -> int:
        """Полностью очищает все товары (используется при reset)."""
        async with get_async_session_factory()() as session:
            result = await session.execute(delete(Item))
            await session.commit()
            return result.rowcount

    @staticmethod
    async def delete_all_categories() -> int:
        """Полностью очищает все категории."""
        async with get_async_session_factory()() as session:
            result = await session.execute(delete(Category))
            await session.commit()
            return result.rowcount

    @staticmethod
    async def get_category_by_id(cat_id: int) -> Category | None:
        async with get_async_session_factory()() as session:
            return await session.get(Category, cat_id)

    @staticmethod
    async def get_item_by_id(item_id: int) -> Item | None:
        async with get_async_session_factory()() as session:
            return await session.get(Item, item_id)

    @staticmethod
    async def count_items_in_category(cat_id: int) -> int:
        """Количество товаров в категории."""
        async with get_async_session_factory()() as session:
            return await session.scalar(
                select(func.count()).select_from(Item)
                .where(Item.category_id == cat_id)
            ) or 0

    @staticmethod
    async def move_items(from_category_id: int, to_category_id: int) -> int:
        """Переносит все товары из одной категории в другую."""
        async with get_async_session_factory()() as session:
            result = await session.execute(
                update(Item)
                .where(Item.category_id == from_category_id)
                .values(category_id=to_category_id)
            )
            await session.commit()
            return result.rowcount

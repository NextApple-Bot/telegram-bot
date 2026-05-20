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
        """Загружает весь ассортимент с группировкой по категориям, отсортированный по sort_order."""
        async with get_async_session_factory()() as session:
            query = (
                select(Category, Item)
                .outerjoin(Item, Category.id == Item.category_id)
                .order_by(Category.sort_order, Item.text)
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
                    "sort_order": cat.sort_order,
                    "items": []
                }

            if item:
                categories[cat_name]["items"].append({
                    "id": item.id,
                    "text": item.text.strip(),
                    "price": getattr(item, 'booking_price', None) or getattr(item, 'sale_price', None),
                    "is_booked": item.is_booked,
                    "booking_info": getattr(item, 'booking_info', None),
                    "serial": item.serial,
                })

        return list(categories.values())

    @staticmethod
    async def import_arrival_from_excel(file_path: str) -> Dict[str, Any]:
        """Импорт нового ассортимента из Excel-файла (прибытие)."""
        try:
            df = pd.read_excel(file_path)

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

                    category = await session.scalar(
                        select(Category).where(Category.name.ilike(category_name))
                    )
                    if not category:
                        category = Category(name=category_name)
                        session.add(category)
                        await session.flush()
                        added_categories += 1

                    existing_item = await session.scalar(
                        select(Item).where(
                            Item.category_id == category.id,
                            Item.text.ilike(item_text)
                        )
                    )

                    if existing_item:
                        if price is not None and getattr(existing_item, 'booking_price', None) != price:
                            existing_item.booking_price = price
                            updated_items += 1
                    else:
                        new_item = Item(
                            text=item_text,
                            category_id=category.id,
                            booking_price=price,
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
    async def import_arrival_from_txt(file_path: str) -> Dict[str, Any]:
        """Импорт нового ассортимента из TXT-файла."""
        try:
            added_categories = 0
            added_items = 0
            updated_items = 0

            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            async with get_async_session_factory()() as session:
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    parts = [p.strip() for p in line.split('|')]
                    if len(parts) < 2:
                        continue

                    category_name = parts[0]
                    item_text = parts[1]
                    price = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None

                    if not category_name or not item_text:
                        continue

                    category = await session.scalar(
                        select(Category).where(Category.name.ilike(category_name))
                    )
                    if not category:
                        category = Category(name=category_name)
                        session.add(category)
                        await session.flush()
                        added_categories += 1

                    existing_item = await session.scalar(
                        select(Item).where(
                            Item.category_id == category.id,
                            Item.text.ilike(item_text)
                        )
                    )

                    if existing_item:
                        if price is not None and getattr(existing_item, 'booking_price', None) != price:
                            existing_item.booking_price = price
                            updated_items += 1
                    else:
                        new_item = Item(
                            text=item_text,
                            category_id=category.id,
                            booking_price=price,
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
            logger.exception("Ошибка импорта из TXT")
            return {"success": False, "error": str(e)}

    @staticmethod
    async def add_category(name: str) -> bool:
        if not name or len(name.strip()) < 2:
            return False
        name = name.strip()
        async with get_async_session_factory()() as session:
            existing = await session.scalar(select(Category).where(Category.name.ilike(name)))
            if existing:
                return False
            category = Category(name=name)
            session.add(category)
            await session.commit()
            return True

    @staticmethod
    async def add_item(text: str, category_id: int, price: int | None = None) -> bool:
        if not text or not category_id:
            return False
        async with get_async_session_factory()() as session:
            category = await session.get(Category, category_id)
            if not category:
                return False
            item = Item(text=text.strip(), category_id=category_id, booking_price=price, is_booked=False)
            session.add(item)
            await session.commit()
            return True

    @staticmethod
    async def delete_all_items() -> int:
        async with get_async_session_factory()() as session:
            result = await session.execute(delete(Item))
            await session.commit()
            return result.rowcount

    @staticmethod
    async def delete_all_categories() -> int:
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
        async with get_async_session_factory()() as session:
            return await session.scalar(
                select(func.count()).select_from(Item).where(Item.category_id == cat_id)
            ) or 0

    @staticmethod
    async def move_items(from_category_id: int, to_category_id: int) -> int:
        async with get_async_session_factory()() as session:
            result = await session.execute(
                update(Item).where(Item.category_id == from_category_id).values(category_id=to_category_id)
            )
            await session.commit()
            return result.rowcount

    @staticmethod
    async def move_category_up(cat_id: int) -> bool:
        """Переместить категорию вверх (уменьшить sort_order)."""
        async with get_async_session_factory()() as session:
            cat = await session.get(Category, cat_id)
            if not cat:
                return False
            # Найти категорию выше
            prev_cat = await session.scalar(
                select(Category).where(Category.sort_order < cat.sort_order).order_by(Category.sort_order.desc()).limit(1)
            )
            if not prev_cat:
                return False
            # Поменять местами
            cat.sort_order, prev_cat.sort_order = prev_cat.sort_order, cat.sort_order
            await session.commit()
            return True

    @staticmethod
    async def move_category_down(cat_id: int) -> bool:
        """Переместить категорию вниз (увеличить sort_order)."""
        async with get_async_session_factory()() as session:
            cat = await session.get(Category, cat_id)
            if not cat:
                return False
            # Найти категорию ниже
            next_cat = await session.scalar(
                select(Category).where(Category.sort_order > cat.sort_order).order_by(Category.sort_order).limit(1)
            )
            if not next_cat:
                return False
            # Поменять местами
            cat.sort_order, next_cat.sort_order = next_cat.sort_order, cat.sort_order
            await session.commit()
            return True

    @staticmethod
    async def reorder_categories(new_order: list[int]) -> bool:
        """Полная перестановка категорий по списку ID."""
        async with get_async_session_factory()() as session:
            for index, cat_id in enumerate(new_order):
                cat = await session.get(Category, cat_id)
                if cat:
                    cat.sort_order = index
            await session.commit()
            return True

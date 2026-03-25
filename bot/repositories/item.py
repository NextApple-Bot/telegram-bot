import logging
import asyncpg
from typing import Optional, List, Dict
from bot.db import get_pool, retry_on_db_error
from bot.utils.validators import extract_serials

logger = logging.getLogger(__name__)

class ItemRepository:
    """Репозиторий для работы с товарами и категориями."""

    @staticmethod
    @retry_on_db_error()
    async def get_or_create_category(name: str) -> int:
        """Возвращает ID категории по имени, создаёт при отсутствии."""
        norm_name = name.lower().rstrip(':')
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow('SELECT id FROM categories WHERE LOWER(name) = $1', norm_name)
            if row:
                return row['id']
            try:
                row = await conn.fetchrow('INSERT INTO categories (name) VALUES ($1) RETURNING id', name)
                return row['id']
            except asyncpg.UniqueViolationError:
                row = await conn.fetchrow('SELECT id FROM categories WHERE name = $1', name)
                if row:
                    return row['id']
                else:
                    logger.error(f"Не удалось создать или найти категорию {name} после UniqueViolation")
                    raise

    @staticmethod
    @retry_on_db_error()
    async def add_item(text: str, serial: Optional[str] = None, category_id: Optional[int] = None, category_name: Optional[str] = None):
        """Добавляет товар. Можно указать category_id или category_name."""
        if category_id is None:
            if category_name is None:
                category_name = "Общее:"
            cat_id = await ItemRepository.get_or_create_category(category_name)
        else:
            cat_id = category_id
        normalized_serial = serial.strip().upper() if serial else None
        is_booked = 'Бронь от' in text
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO items (text, serial, category_id, is_booked)
                VALUES ($1, $2, $3, $4)
            ''', text, normalized_serial, cat_id, is_booked)

    @staticmethod
    @retry_on_db_error()
    async def get_item_id_by_serial(serial: str) -> Optional[int]:
        if not serial:
            return None
        normalized = serial.strip().upper()
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow('SELECT id FROM items WHERE UPPER(serial) = $1', normalized)
            return row['id'] if row else None

    @staticmethod
    @retry_on_db_error()
    async def get_item_by_serial(serial: str) -> Optional[Dict]:
        normalized = serial.strip().upper()
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT i.id, i.text, c.id as category_id, c.name as category_name
                FROM items i
                JOIN categories c ON i.category_id = c.id
                WHERE UPPER(i.serial) = $1
            ''', normalized)
            return dict(row) if row else None

    @staticmethod
    @retry_on_db_error()
    async def get_item_by_text(text: str) -> Optional[Dict]:
        """Ищет товар по точному тексту, возвращает id, текст и имя категории."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT i.id, i.text, c.name as category_name
                FROM items i
                JOIN categories c ON i.category_id = c.id
                WHERE i.text = $1
            ''', text)
            return dict(row) if row else None

    @staticmethod
    @retry_on_db_error()
    async def remove_item_by_serial(serial: str) -> int:
        normalized = serial.strip().upper() if serial else None
        pool = await get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute('DELETE FROM items WHERE UPPER(serial) = $1', normalized)
            return int(result.split()[1]) if result.startswith('DELETE') else 0

    @staticmethod
    @retry_on_db_error()
    async def get_all_categories_with_items():
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT c.name as category_name, i.text as item_text
                FROM categories c
                LEFT JOIN items i ON c.id = i.category_id
                ORDER BY c.id, i.id
            ''')
            categories = {}
            for row in rows:
                cat = row['category_name']
                if cat not in categories:
                    categories[cat] = []
                if row['item_text']:
                    categories[cat].append(row['item_text'])
            return [{"header": cat, "items": items} for cat, items in categories.items()]

    @staticmethod
    @retry_on_db_error()
    async def get_all_items_serials():
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('SELECT text, serial FROM items')
            return [dict(row) for row in rows]

    # ========== НОВЫЙ МЕТОД ДЛЯ МАССОВОЙ ЗАМЕНЫ АССОРТИМЕНТА ==========
    @staticmethod
    @retry_on_db_error()
    async def bulk_replace_assortment(categories: List[Dict[str, List[str]]]) -> None:
        """
        Полностью заменяет ассортимент: очищает таблицы и вставляет новые данные.
        Использует COPY для максимальной скорости.
        """
        from bot.services.assortment import AssortmentService
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # 1. Очищаем всё (каскадное удаление)
                await conn.execute('TRUNCATE TABLE categories CASCADE')
                # 2. Вставляем категории
                category_names = [cat['header'] for cat in categories]
                async with conn.copy_records_to_table('categories', columns=['name']) as copy:
                    for name in category_names:
                        await copy.write_row((name,))
                # 3. Получаем id категорий
                rows = await conn.fetch('SELECT id, name FROM categories')
                cat_id_map = {row['name']: row['id'] for row in rows}
                # 4. Подготавливаем данные для товаров
                items_data = []
                for cat in categories:
                    cat_id = cat_id_map[cat['header']]
                    for item_text in cat['items']:
                        serials = extract_serials(item_text)
                        serial = serials[0].strip().upper() if serials else None
                        is_booked = 'Бронь от' in item_text
                        items_data.append((item_text, serial, cat_id, is_booked))
                # 5. Вставляем товары пакетно
                if items_data:
                    async with conn.copy_records_to_table('items', columns=['text', 'serial', 'category_id', 'is_booked']) as copy:
                        for row in items_data:
                            await copy.write_row(row)
        AssortmentService.invalidate_cache()

    # ========== СТАРЫЙ МЕТОД update_category_items — УДАЛЁН, ИСПОЛЬЗУЙТЕ bulk_replace_assortment ==========

    @staticmethod
    @retry_on_db_error()
    async def clear_all_inventory():
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute('DELETE FROM categories')

    @staticmethod
    @retry_on_db_error()
    async def add_deleted_item(item_id: int, text: str, serial: str, category_id: int, reason: str = 'manual'):
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO deleted_items (item_id, text, serial, category_id, reason)
                VALUES ($1, $2, $3, $4, $5)
            ''', item_id, text, serial, category_id, reason)

    @staticmethod
    @retry_on_db_error()
    async def get_last_deleted_item() -> Optional[Dict]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT * FROM deleted_items
                WHERE restored = FALSE
                ORDER BY deleted_at DESC
                LIMIT 1
            ''')
            return dict(row) if row else None

    @staticmethod
    @retry_on_db_error()
    async def restore_deleted_item(deleted_id: int) -> bool:
        pool = await get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute('UPDATE deleted_items SET restored = TRUE WHERE id = $1', deleted_id)
            return result == "UPDATE 1"

    @staticmethod
    @retry_on_db_error()
    async def mark_item_booked(item_id: int, book_text: str):
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                UPDATE items SET text = $1, is_booked = TRUE WHERE id = $2
            ''', book_text, item_id)

import pytest
from bot.repositories import ItemRepository
from bot.services.assortment import AssortmentService
from bot.db import get_pool


@pytest.mark.asyncio
async def test_restore_via_undo_command(db_conn):
    # Подготовка: категория, товар
    await db_conn.execute("""
        INSERT INTO categories (name, sort_order) VALUES ('Samsung', 1)
    """)
    cat_id = await db_conn.fetchval("SELECT id FROM categories WHERE name='Samsung'")
    await db_conn.execute("""
        INSERT INTO items (text, serial, category_id) VALUES ('Galaxy S24', 'S24XYZ', $1)
    """, cat_id)
    item_id = await db_conn.fetchval("SELECT id FROM items WHERE serial='S24XYZ'")

    # Удаляем товар (имитация продажи)
    deleted = await AssortmentService.remove_by_serial('S24XYZ', reason='test')
    assert deleted == 1

    # Проверяем, что товар в deleted_items
    deleted_rec = await db_conn.fetchrow("SELECT * FROM deleted_items WHERE serial='S24XYZ'")
    assert deleted_rec is not None

    # Восстанавливаем через ItemRepository.restore_deleted_item
    restored = await ItemRepository.restore_deleted_item(deleted_rec['id'])
    assert restored is True

    # Товар должен появиться в items
    item = await db_conn.fetchrow("SELECT * FROM items WHERE serial='S24XYZ'")
    assert item is not None
    assert item['text'] == 'Galaxy S24'

    # Запись в deleted_items должна быть помечена restored
    updated = await db_conn.fetchrow("SELECT restored FROM deleted_items WHERE id=$1", deleted_rec['id'])
    assert updated['restored'] is True

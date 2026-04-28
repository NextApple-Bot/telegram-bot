import pytest
from bot.repositories import ItemRepository
from bot.services.assortment import AssortmentService
from bot.db import get_pool


@pytest.mark.asyncio
async def test_restore_via_undo_command(db_conn):
    await db_conn.execute("""
        INSERT INTO categories (name, sort_order) VALUES ('Samsung', 1)
    """)
    cat_id = await db_conn.fetchval("SELECT id FROM categories WHERE name='Samsung'")
    await db_conn.execute("""
        INSERT INTO items (text, serial, category_id) VALUES ('Galaxy S24', 'S24XYZ', $1)
    """, cat_id)
    # Исправлено: переменная не используется -> удалено присвоение
    _ = await db_conn.fetchval("SELECT id FROM items WHERE serial='S24XYZ'")  # или можно просто удалить строку

    deleted = await AssortmentService.remove_by_serial('S24XYZ', reason='test')
    assert deleted == 1

    deleted_rec = await db_conn.fetchrow("SELECT * FROM deleted_items WHERE serial='S24XYZ'")
    assert deleted_rec is not None

    restored = await ItemRepository.restore_deleted_item(deleted_rec['id'])
    assert restored is True

    item = await db_conn.fetchrow("SELECT * FROM items WHERE serial='S24XYZ'")
    assert item is not None
    assert item['text'] == 'Galaxy S24'

    updated = await db_conn.fetchrow("SELECT restored FROM deleted_items WHERE id=$1", deleted_rec['id'])
    assert updated['restored'] is True

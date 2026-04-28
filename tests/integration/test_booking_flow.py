import pytest
from bot.handlers.topics.preorder import router
from bot.db import get_pool
from aiogram.types import Message, Chat, User


@pytest.mark.asyncio
async def test_booking_flow_success(mock_bot, db_conn):
    # Подготовка: товар
    await db_conn.execute("""
        INSERT INTO categories (name, sort_order) VALUES ('iPad', 1)
    """)
    cat_id = await db_conn.fetchval("SELECT id FROM categories WHERE name='iPad'")
    await db_conn.execute("""
        INSERT INTO items (text, serial, category_id, is_booked)
        VALUES ('iPad Pro 11', 'IPAD789', $1, false)
    """, cat_id)

    # Сообщение с бронированием
    content = """БРОНЬ:
iPad Pro 11 (IPAD789) - 80000₽
П/О 20000 (нал)
Клиент: Петр Петров
Телефон: +79123456789
Площадка: Авито"""
    message = Message(
        message_id=456,
        chat=Chat(id=config.MAIN_GROUP_ID, type="supergroup"),
        text=content,
        message_thread_id=config.THREAD_PREORDER,
        from_user=User(id=12345, is_bot=False, first_name="Admin")
    )

    from bot.handlers.topics.preorder import handle_preorder
    await handle_preorder(message)

    # Проверки
    item = await db_conn.fetchrow("SELECT * FROM items WHERE serial='IPAD789'")
    assert item is not None
    assert item['is_booked'] is True
    assert "Бронь от" in item['text']

    # Проверка bookings
    booking = await db_conn.fetchrow("SELECT * FROM bookings WHERE item_id=$1", item['id'])
    assert booking is not None
    assert booking['total_amount'] == 80000.0

    # Проверка daily_payments (предоплата)
    payment = await db_conn.fetchrow("SELECT * FROM daily_payments WHERE type='preorder' AND amount=20000")
    assert payment is not None
    assert payment['payment_type'] == 'cash'

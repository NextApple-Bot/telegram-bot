import pytest
from aiogram.types import Chat, Message, User

from bot import config  # Добавлено


@pytest.mark.asyncio
async def test_sale_flow_success(mock_bot, db_conn):
    # 1. Подготовка: добавим товар в ассортимент
    await db_conn.execute("""
        INSERT INTO categories (name, sort_order) VALUES ('iPhone', 1)
    """)
    cat_id = await db_conn.fetchval("SELECT id FROM categories WHERE name='iPhone'")
    await db_conn.execute("""
        INSERT INTO items (text, serial, category_id, is_booked)
        VALUES ('iPhone 15 Pro', 'ABC123', $1, false)
    """, cat_id)

    # 2. Создаём сообщение в топике продаж
    content = """iPhone 15 Pro (ABC123) - 120000₽
Наличные - 120000
Клиент: Иван Иванов
Телефон: +79991234567"""
    message = Message(
        message_id=123,
        chat=Chat(id=config.MAIN_GROUP_ID, type="supergroup"),
        text=content,
        message_thread_id=config.THREAD_SALES,
        from_user=User(id=12345, is_bot=False, first_name="Admin")
    )

    # 3. Обрабатываем сообщение
    from bot.handlers.topics.sales import handle_sales_message
    await handle_sales_message(message, mock_bot)

    # 4. Проверки
    item = await db_conn.fetchrow("SELECT * FROM items WHERE serial='ABC123'")
    assert item is None

    deleted = await db_conn.fetchrow("SELECT * FROM deleted_items WHERE serial='ABC123'")
    assert deleted is not None
    assert deleted['reason'] == 'sale'

    sale = await db_conn.fetchrow("SELECT * FROM sales WHERE message_id=$1", message.message_id)
    assert sale is not None
    assert sale['cash'] == 120000.0

    payment = await db_conn.fetchrow("SELECT * FROM daily_payments WHERE sale_message_id=$1", message.message_id)
    assert payment is not None
    assert payment['payment_type'] == 'cash'
    assert payment['amount'] == 120000.0

    client = await db_conn.fetchrow("SELECT * FROM clients WHERE phone='+79991234567'")
    assert client is not None
    assert client['full_name'] == 'Иван Иванов'

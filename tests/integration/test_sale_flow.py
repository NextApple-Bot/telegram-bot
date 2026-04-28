import pytest
from bot.handlers.topics.sales import router
from bot.services.assortment import AssortmentService
from bot.db import get_pool
from bot.utils.parser import extract_payment_amounts
from aiogram.types import Message, Chat, User


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

    # 3. Обрабатываем сообщение (имитация вызова хендлера)
    from aiogram import Dispatcher
    dp = Dispatcher()
    dp.include_router(router)
    # Эмуляция вызова: напрямую вызываем хендлер
    from bot.handlers.topics.sales import handle_sales_message
    await handle_sales_message(message, mock_bot)

    # 4. Проверки
    # Товар должен быть удалён из items
    item = await db_conn.fetchrow("SELECT * FROM items WHERE serial='ABC123'")
    assert item is None

    # Должна быть запись в deleted_items
    deleted = await db_conn.fetchrow("SELECT * FROM deleted_items WHERE serial='ABC123'")
    assert deleted is not None
    assert deleted['reason'] == 'sale'

    # Должна быть запись в sales с message_id
    sale = await db_conn.fetchrow("SELECT * FROM sales WHERE message_id=$1", message.message_id)
    assert sale is not None
    assert sale['cash'] == 120000.0

    # Должна быть запись в daily_payments
    payment = await db_conn.fetchrow("SELECT * FROM daily_payments WHERE sale_message_id=$1", message.message_id)
    assert payment is not None
    assert payment['payment_type'] == 'cash'
    assert payment['amount'] == 120000.0

    # Должен быть создан клиент
    client = await db_conn.fetchrow("SELECT * FROM clients WHERE phone='+79991234567'")
    assert client is not None
    assert client['full_name'] == 'Иван Иванов'

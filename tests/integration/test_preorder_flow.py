import pytest
from bot import config  # Добавлено
from bot.handlers.topics.preorder import router
from bot.db import get_pool
from aiogram.types import Message, Chat, User


@pytest.mark.asyncio
async def test_preorder_only_payments(mock_bot, db_conn):
    content = """П/О 5000 (терминал)
Клиент: Сергей Сергеев
Телефон: +79876543210"""
    message = Message(
        message_id=789,
        chat=Chat(id=config.MAIN_GROUP_ID, type="supergroup"),
        text=content,
        message_thread_id=config.THREAD_PREORDER,
        from_user=User(id=12345, is_bot=False, first_name="Admin")
    )

    from bot.handlers.topics.preorder import handle_preorder
    await handle_preorder(message)

    preorder = await db_conn.fetchrow("SELECT * FROM preorders ORDER BY id DESC LIMIT 1")
    assert preorder is not None
    assert preorder['terminal'] == 5000.0

    payment = await db_conn.fetchrow("SELECT * FROM daily_payments WHERE type='preorder' AND amount=5000")
    assert payment is not None
    assert payment['payment_type'] == 'terminal'

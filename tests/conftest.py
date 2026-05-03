import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

# Отключаем uvloop глобально до любых импортов aiogram
try:
    import uvloop
    uvloop.install = lambda: None
except ImportError:
    pass

os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost/db"
os.environ.setdefault("REDIS_URL", "")
os.environ["SCALING_ENABLED"] = "false"
os.environ["BOT_TOKEN"] = "test_token"
os.environ["ADMIN_ID"] = "123"
os.environ["MAIN_GROUP_ID"] = "-100123"
os.environ["THREAD_SALES"] = "1"
os.environ["THREAD_ASSORTMENT"] = "2"
os.environ["THREAD_ARRIVAL"] = "3"
os.environ["THREAD_PREORDER"] = "4"
os.environ["SECRET_KEY"] = "dummy_secret_key_for_testing_only_min_32_chars"
os.environ["ADMIN_PASSWORD"] = "testpass"


@pytest.fixture
def mock_bot():
    """Создаёт AsyncMock для aiogram.Bot."""
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=AsyncMock(message_id=1))
    bot.send_document = AsyncMock(return_value=AsyncMock(message_id=2))
    bot.delete_message = AsyncMock()
    bot.react = AsyncMock()
    bot.get_me = AsyncMock(return_value=AsyncMock(username="test_bot"))
    bot.delete_webhook = AsyncMock()
    bot.set_webhook = AsyncMock()
    bot.session = AsyncMock()
    bot.session.close = AsyncMock()
    return bot


@pytest.fixture
def mock_state():
    """Создаёт AsyncMock для FSMContext."""
    state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.clear = AsyncMock()
    return state


@pytest.fixture(autouse=True)
def reset_environment():
    """Сбрасывает важные глобальные состояния перед каждым тестом."""
    # Патчим bot.db.get_pool, чтобы случайно не обращаться к реальной БД
    with patch('bot.db.get_pool', new=AsyncMock()):
        yield

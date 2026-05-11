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


@pytest.fixture(autouse=True)
def mock_db_session():
    """Подменяет get_async_session_factory на мок, возвращающий AsyncMock-сессию."""
    mock_session = AsyncMock()
    mock_session_factory = AsyncMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session

    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()

    with patch('bot.db.get_async_session_factory', return_value=mock_session_factory):
        yield


@pytest.fixture
def mock_bot():
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
    state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.clear = AsyncMock()
    return state

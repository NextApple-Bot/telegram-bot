import pytest
import asyncio
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

# Фикстура для создания event loop
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

# Фикстура для мока пула БД
@pytest.fixture
async def mock_db_pool():
    with patch('bot.db.get_pool') as mock_get_pool:
        mock_conn = AsyncMock()
        mock_pool = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_get_pool.return_value = mock_pool
        yield mock_conn

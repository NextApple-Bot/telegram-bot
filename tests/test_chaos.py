from unittest.mock import patch

import pytest

from bot.services.cache import cache


@pytest.mark.asyncio
async def test_redis_failure_get():
    with patch.object(cache._redis, 'get', side_effect=ConnectionError):
        result = await cache.get("any_key")
        assert result is None


@pytest.mark.asyncio
async def test_redis_failure_set():
    with patch.object(cache._redis, 'set', side_effect=ConnectionError):
        # Не должно падать
        await cache.set("key", "value")


@pytest.mark.asyncio
async def test_redis_not_configured():
    with patch.object(cache, '_enabled', False):
        result = await cache.get("key")
        assert result is None
        await cache.set("key", "value")  # не падает

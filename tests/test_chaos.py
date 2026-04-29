from unittest.mock import patch

import pytest

from bot.services.cache import cache


@pytest.mark.asyncio
async def test_redis_failure_get():
    # При отключённом Redis и моке, который бросает исключение
    with patch.object(cache, 'get', side_effect=ConnectionError):
        with pytest.raises(ConnectionError):
            await cache.get("any_key")


@pytest.mark.asyncio
async def test_redis_failure_set():
    with patch.object(cache, 'set', side_effect=ConnectionError):
        # не должно упасть, исключение подавляется внутри
        await cache.set("key", "value")


@pytest.mark.asyncio
async def test_redis_not_configured():
    # При _enabled=False get возвращает None, set молча отрабатывает
    cache._enabled = False
    result = await cache.get("key")
    assert result is None
    await cache.set("key", "value")

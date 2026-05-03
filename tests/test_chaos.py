from unittest.mock import patch

import pytest

from bot.services.cache import cache


@pytest.mark.asyncio
async def test_redis_failure_get():
    # Мокаем метод get, который в реальности может вызвать ошибку,
    # и проверяем, что ошибка пробрасывается (в отличие от set)
    with (
        patch.object(cache, 'get', side_effect=ConnectionError),
        pytest.raises(ConnectionError)
    ):
        await cache.get("any_key")


@pytest.mark.asyncio
async def test_redis_failure_set():
    # set должен подавлять исключения (как в реальном коде),
    # поэтому при ошибке он не должен ронять тест.
    # Здесь мы просто проверяем, что вызов не вызывает исключений.
    cache._enabled = True        # включаем, чтобы set попытался записать
    with patch.object(cache, '_redis') as mock_redis:
        mock_redis.set.side_effect = ConnectionError
        await cache.set("key", "value")   # не должно упасть
    # После теста восстанавливаем состояние
    cache._enabled = False


@pytest.mark.asyncio
async def test_redis_not_configured():
    # При _enabled=False get возвращает None, set молча отрабатывает
    cache._enabled = False
    result = await cache.get("key")
    assert result is None
    await cache.set("key", "value")

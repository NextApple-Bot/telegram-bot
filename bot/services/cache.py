import json
import logging
from typing import Any

import redis.asyncio as redis
from redis.exceptions import RedisError, ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError

from bot import config

logger = logging.getLogger(__name__)


class RedisCache:
    """Обёртка над Redis для кэширования данных (ассортимент, топ-модели, статистика)."""

    def __init__(self):
        self._redis: redis.Redis | None = None
        self._enabled = bool(config.REDIS_URL)
        if self._enabled:
            self._redis = redis.from_url(config.REDIS_URL, decode_responses=True)
            logger.info("✅ RedisCache инициализирован")
        else:
            logger.warning("⚠️ REDIS_URL не задан, кэширование отключено")

    async def get(self, key: str) -> Any | None:
        if not self._enabled or not self._redis:
            return None
        try:
            data = await self._redis.get(key)
            if data:
                return json.loads(data)
        except (RedisError, RedisConnectionError, RedisTimeoutError) as e:
            logger.error(f"Redis get error for key {key}: {e}", exc_info=True)
        return None

    async def set(self, key: str, value: Any, ttl: int = 60):
        if not self._enabled or not self._redis:
            return
        try:
            await self._redis.set(key, json.dumps(value, default=str), ex=ttl)
        except (RedisError, RedisConnectionError, RedisTimeoutError) as e:
            logger.error(f"Redis set error for key {key}: {e}", exc_info=True)

    async def delete(self, key: str):
        if not self._enabled or not self._redis:
            return
        try:
            await self._redis.delete(key)
        except (RedisError, RedisConnectionError, RedisTimeoutError) as e:
            logger.error(f"Redis delete error for key {key}: {e}", exc_info=True)

    async def clear_pattern(self, pattern: str):
        if not self._enabled or not self._redis:
            return
        try:
            keys = await self._redis.keys(pattern)
            if keys:
                await self._redis.delete(*keys)
        except (RedisError, RedisConnectionError, RedisTimeoutError) as e:
            logger.error(f"Redis clear pattern error: {e}", exc_info=True)

    # Блокировки
    async def lock(self, key: str, ttl: int = 60, value: str = "locked") -> bool:
        if not self._enabled or not self._redis:
            logger.warning("Redis не доступен, блокировка не работает — возможны гонки")
            return True
        try:
            acquired = await self._redis.set(key, value, nx=True, ex=ttl)
            return acquired is not None
        except (RedisError, RedisConnectionError, RedisTimeoutError) as e:
            logger.error(f"Ошибка lock Redis: {e}", exc_info=True)
            return True  # на ошибке лучше выполнить, чем заблокировать навсегда

    async def unlock(self, key: str) -> None:
        if self._enabled and self._redis:
            try:
                await self._redis.delete(key)
            except (RedisError, RedisConnectionError, RedisTimeoutError) as e:
                logger.error(f"Ошибка unlock Redis: {e}", exc_info=True)


# Глобальный экземпляр
cache = RedisCache()

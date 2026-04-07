# Файл: bot/services/cache.py
import json
import logging
from typing import Any, Optional
import redis.asyncio as redis
from bot import config

logger = logging.getLogger(__name__)


class RedisCache:
    """Обёртка над Redis для кэширования данных (ассортимент, топ-модели, статистика)."""

    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self._enabled = bool(config.REDIS_URL)
        if self._enabled:
            self._redis = redis.from_url(config.REDIS_URL, decode_responses=True)
            logger.info("✅ RedisCache инициализирован")
        else:
            logger.warning("⚠️ REDIS_URL не задан, кэширование отключено")

    async def get(self, key: str) -> Optional[Any]:
        if not self._enabled:
            return None
        try:
            data = await self._redis.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Redis get error for key {key}: {e}")
        return None

    async def set(self, key: str, value: Any, ttl: int = 60):
        if not self._enabled:
            return
        try:
            await self._redis.set(key, json.dumps(value, default=str), ex=ttl)
        except Exception as e:
            logger.error(f"Redis set error for key {key}: {e}")

    async def delete(self, key: str):
        if not self._enabled:
            return
        try:
            await self._redis.delete(key)
        except Exception as e:
            logger.error(f"Redis delete error for key {key}: {e}")

    async def clear_pattern(self, pattern: str):
        if not self._enabled:
            return
        try:
            keys = await self._redis.keys(pattern)
            if keys:
                await self._redis.delete(*keys)
        except Exception as e:
            logger.error(f"Redis clear pattern error: {e}")


# Глобальный экземпляр
cache = RedisCache()

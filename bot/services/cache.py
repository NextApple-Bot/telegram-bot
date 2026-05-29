import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

class RedisCache:
    def __init__(self):
        self._redis = None
        self._enabled = bool(os.getenv("REDIS_URL"))
        if self._enabled:
            try:
                import redis.asyncio as redis
                self._redis = redis.from_url(os.getenv("REDIS_URL"), decode_responses=True)
                logger.info("✅ RedisCache инициализирован")
            except Exception as e:
                logger.error(f"Не удалось подключиться к Redis: {e}")
                self._enabled = False
        else:
            logger.warning("⚠️ REDIS_URL не задан, кэширование отключено")

    async def get(self, key: str) -> Optional[Any]:
        if not self._enabled or not self._redis:
            return None
        try:
            data = await self._redis.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Redis get error: {e}")
        return None

    async def set(self, key: str, value: Any, ttl: int = 60):
        if not self._enabled or not self._redis:
            return
        try:
            await self._redis.set(key, json.dumps(value, default=str), ex=ttl)
        except Exception as e:
            logger.error(f"Redis set error: {e}")

    async def delete(self, key: str):
        if not self._enabled or not self._redis:
            return
        try:
            await self._redis.delete(key)
        except Exception as e:
            logger.error(f"Redis delete error: {e}")

    async def clear_pattern(self, pattern: str):
        if not self._enabled or not self._redis:
            return
        try:
            keys = await self._redis.keys(pattern)
            if keys:
                await self._redis.delete(*keys)
        except Exception as e:
            logger.error(f"Redis clear pattern error: {e}")


cache = RedisCache()

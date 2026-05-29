import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


class RedisCache:
    """Кэш на Redis с безопасной инициализацией."""

    def __init__(self):
        self._redis = None
        redis_url = os.getenv("REDIS_URL")

        self._enabled = bool(redis_url)

        if self._enabled:
            try:
                import redis.asyncio as redis
                self._redis = redis.from_url(redis_url, decode_responses=True)
                logger.info("✅ RedisCache успешно подключён")
            except Exception as e:
                logger.error(f"❌ Не удалось подключиться к Redis: {e}")
                self._enabled = False
        else:
            logger.warning("⚠️ REDIS_URL не задан — кэширование отключено")

    async def get(self, key: str) -> Optional[Any]:
        if not self._enabled or not self._redis:
            return None
        try:
            data = await self._redis.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Redis GET error ({key}): {e}")
            return None

    async def set(self, key: str, value: Any, ttl: int = 60):
        if not self._enabled or not self._redis:
            return
        try:
            await self._redis.set(key, json.dumps(value, default=str), ex=ttl)
        except Exception as e:
            logger.error(f"Redis SET error ({key}): {e}")

    async def delete(self, key: str):
        if not self._enabled or not self._redis:
            return
        try:
            await self._redis.delete(key)
        except Exception as e:
            logger.error(f"Redis DELETE error ({key}): {e}")

    async def clear_pattern(self, pattern: str):
        if not self._enabled or not self._redis:
            return
        try:
            keys = await self._redis.keys(pattern)
            if keys:
                await self._redis.delete(*keys)
        except Exception as e:
            logger.error(f"Redis clear_pattern error: {e}")


# Глобальный экземпляр
cache = RedisCache()

# Файл: bot/services/cache.py
import json
import logging
from typing import Any, Optional
import redis.asyncio as redis
from bot import config

logger = logging.getLogger(__name__)

class RedisCache:
    """Обёртка для Redis с методами get/set/delete с сериализацией JSON."""
    _client: Optional[redis.Redis] = None

    @classmethod
    async def get_client(cls) -> redis.Redis:
        if cls._client is None:
            if not config.REDIS_URL:
                logger.warning("REDIS_URL не задан, кэш через Redis не работает")
                return None
            cls._client = redis.from_url(config.REDIS_URL, decode_responses=True)
        return cls._client

    @classmethod
    async def get(cls, key: str) -> Any:
        client = await cls.get_client()
        if not client:
            return None
        try:
            data = await client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Ошибка чтения из Redis: {e}")
        return None

    @classmethod
    async def set(cls, key: str, value: Any, ttl: int = 300) -> bool:
        client = await cls.get_client()
        if not client:
            return False
        try:
            await client.set(key, json.dumps(value, default=str), ex=ttl)
            return True
        except Exception as e:
            logger.error(f"Ошибка записи в Redis: {e}")
            return False

    @classmethod
    async def delete(cls, key: str) -> bool:
        client = await cls.get_client()
        if not client:
            return False
        try:
            await client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления из Redis: {e}")
            return False

    @classmethod
    async def invalidate_pattern(cls, pattern: str) -> None:
        """Удаляет все ключи, соответствующие шаблону (например, 'assortment:*')."""
        client = await cls.get_client()
        if not client:
            return
        try:
            keys = await client.keys(pattern)
            if keys:
                await client.delete(*keys)
        except Exception as e:
            logger.error(f"Ошибка инвалидации паттерна {pattern}: {e}")

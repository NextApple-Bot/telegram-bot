# Файл: bot/services/assortment.py
import logging
import asyncio
from bot.repositories import ItemRepository

logger = logging.getLogger(__name__)

class AssortmentService:
    _cache = {"data": None, "timestamp": 0, "loading": False}
    CACHE_TTL = 10
    _cache_lock = asyncio.Lock()

    @classmethod
    def invalidate_cache(cls):
        """Сбрасывает кэш."""
        cls._cache["data"] = None
        cls._cache["timestamp"] = 0
        logger.debug("Кэш ассортимента инвалидирован")

    @classmethod
    async def load_inventory(cls):
        """Загружает ассортимент с кэшированием, блокируя одновременную загрузку."""
        import time
        now = time.time()
        
        # Быстрая проверка без блокировки
        if cls._cache["data"] and (now - cls._cache["timestamp"]) < cls.CACHE_TTL:
            return cls._cache["data"]
        
        async with cls._cache_lock:
            # Повторная проверка после получения блокировки
            if cls._cache["data"] and (now - cls._cache["timestamp"]) < cls.CACHE_TTL:
                return cls._cache["data"]
            
            # Загрузка данных
            logger.debug("Загрузка ассортимента из БД")
            categories = await ItemRepository.get_all_categories_with_items()
            cls._cache["data"] = categories
            cls._cache["timestamp"] = now
            return categories

# Файл: bot/services/assortment.py
import logging
import asyncio
from bot.repositories import ItemRepository

logger = logging.getLogger(__name__)

class AssortmentService:
    _cache = {"data": None, "timestamp": 0, "loading": False}
    CACHE_TTL = 300  # увеличен с 10 до 300 секунд (5 минут)
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

    @classmethod
    async def remove_by_serial(cls, serial: str, reason: str = 'sale', conn=None):
        """
        Удаляет товар по серийному номеру с сохранением в deleted_items.
        
        Args:
            serial: Серийный номер товара
            reason: Причина удаления ('sale', 'manual', 'admin_manual')
            conn: Опциональное соединение с БД (для использования в транзакциях)
        """
        if not serial:
            logger.warning("Попытка удалить товар с пустым серийным номером")
            return False
        
        # Получаем информацию о товаре
        if conn is None:
            item_info = await ItemRepository.get_item_by_serial(serial)
        else:
            item_info = await ItemRepository.get_item_by_serial(serial, conn=conn)
        
        if not item_info:
            logger.warning(f"Товар с серийным номером {serial} не найден при удалении")
            return False
        
        item_id = item_info['id']
        item_text = item_info['text']
        category_id = item_info['category_id']
        
        # Сохраняем в deleted_items
        if conn is None:
            await ItemRepository.add_deleted_item(
                item_id=item_id,
                text=item_text,
                serial=serial,
                category_id=category_id,
                reason=reason
            )
            # Удаляем из items
            deleted = await ItemRepository.remove_item_by_serial(serial)
        else:
            await ItemRepository.add_deleted_item(
                item_id=item_id,
                text=item_text,
                serial=serial,
                category_id=category_id,
                reason=reason,
                conn=conn
            )
            deleted = await ItemRepository.remove_item_by_serial(serial, conn=conn)
        
        # Инвалидируем кэш
        cls.invalidate_cache()
        
        logger.info(f"Товар удалён: {item_text} (серийник: {serial}), причина: {reason}")
        return deleted > 0

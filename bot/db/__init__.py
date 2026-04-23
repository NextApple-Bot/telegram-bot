# Файл: bot/db/__init__.py
# Экспорт функций из bot/db.py
from ..db import (
    get_pool,
    close_pool,
    init_db,
    check_db_health,
    check_redis_health,
    retry_on_db_error,
)

# Экспорт ORM-моделей из bot/db/models.py
from .models import (
    Base,
    Client,
    Purchase,
    Category,
    Item,
    Sale,
    Preorder,
    Booking,
    DailyPayment,
    ProcessedMessage,
    DeletedItem,
)

__all__ = [
    # Функции
    'get_pool',
    'close_pool',
    'init_db',
    'check_db_health',
    'check_redis_health',
    'retry_on_db_error',
    # Модели
    'Base',
    'Client',
    'Purchase',
    'Category',
    'Item',
    'Sale',
    'Preorder',
    'Booking',
    'DailyPayment',
    'ProcessedMessage',
    'DeletedItem',
]

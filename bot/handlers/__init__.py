from .base import router
from . import commands
from . import callbacks            # <--- обязательно
from .topics import assortment_router, arrival_router, preorder_router, sales_router

# Подключаем все роутеры
router.include_router(commands.router)
router.include_router(callbacks.router)   # <--- добавляем, если callbacks использует свой роутер (но он использует общий router из base, поэтому достаточно импорта)
router.include_router(assortment_router)
router.include_router(arrival_router)
router.include_router(preorder_router)
router.include_router(sales_router)

__all__ = ['router']

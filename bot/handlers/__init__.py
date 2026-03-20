from .base import router
from . import commands
from . import callbacks            # <--- обязательно добавить эту строку
from .topics import assortment_router, arrival_router, preorder_router, sales_router

# Подключаем все роутеры
router.include_router(commands.router)
router.include_router(assortment_router)
router.include_router(arrival_router)
router.include_router(preorder_router)
router.include_router(sales_router)

__all__ = ['router']

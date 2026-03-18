from .base import router
from . import commands
from .topics import assortment_router, arrival_router, preorder_router, sales_router

# Подключаем роутеры
router.include_router(commands.router)
router.include_router(assortment_router)
router.include_router(arrival_router)
router.include_router(preorder_router)
router.include_router(sales_router)

# НЕ подключаем callbacks.router – он уже включен через base

__all__ = ['router']

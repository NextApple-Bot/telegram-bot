from .base import router
from . import commands
from .topics import assortment_router, arrival_router, preorder_router, sales_router

# Подключаем только те роутеры, которые созданы как отдельные объекты
router.include_router(commands.router)
router.include_router(assortment_router)
router.include_router(arrival_router)
router.include_router(preorder_router)
router.include_router(sales_router)

# ВАЖНО: не подключаем callbacks.router, так как он использует тот же router из base

__all__ = ['router']

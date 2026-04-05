# Файл: bot/handlers/__init__.py
from .base import router
from . import commands
from . import callbacks
from .topics import assortment_router, arrival_router, preorder_router, sales_router
from . import admin_migration

router.include_router(commands.router)
router.include_router(callbacks.router)
router.include_router(assortment_router)
router.include_router(arrival_router)
router.include_router(preorder_router)
router.include_router(sales_router)
router.include_router(admin_migration.router)

__all__ = ['router']

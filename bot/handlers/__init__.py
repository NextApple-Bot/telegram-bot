from .base import router

# topics
from .topics import assortment_router, arrival_router, preorder_router, sales_router
router.include_router(assortment_router)
router.include_router(arrival_router)
router.include_router(preorder_router)
router.include_router(sales_router)

# commands
from . import commands
router.include_router(commands.router)

# callbacks
from . import callbacks
router.include_router(callbacks.router)

# admin_migration (if needed)
from . import admin_migration
router.include_router(admin_migration.router)

__all__ = ['router']
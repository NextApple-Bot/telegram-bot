# Файл: bot/handlers/__init__.py
import logging
from .base import router

logger = logging.getLogger(__name__)

# Пытаемся подключить каждый роутер с явным логом
try:
    from . import commands
    router.include_router(commands.router)
    logger.info("✅ commands.router загружен")
except Exception as e:
    logger.critical(f"❌ Не удалось загрузить commands.router: {e}", exc_info=True)

try:
    from . import callbacks
    router.include_router(callbacks.router)
    logger.info("✅ callbacks.router загружен")
except Exception as e:
    logger.critical(f"❌ Не удалось загрузить callbacks.router: {e}", exc_info=True)

try:
    from .topics import assortment_router, arrival_router, preorder_router, sales_router
    router.include_router(assortment_router)
    router.include_router(arrival_router)
    router.include_router(preorder_router)
    router.include_router(sales_router)
    logger.info("✅ topics routers загружены")
except Exception as e:
    logger.critical(f"❌ Не удалось загрузить topics routers: {e}", exc_info=True)

try:
    from . import admin_migration
    router.include_router(admin_migration.router)
    logger.info("✅ admin_migration загружен")
except Exception as e:
    logger.critical(f"❌ Не удалось загрузить admin_migration: {e}", exc_info=True)

__all__ = ['router']

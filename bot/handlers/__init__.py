from aiogram import Router

from .base import router as base_router
from .commands import router as commands_router
from .callbacks import router as callbacks_router

# Главный роутер
router = Router()

# Подключаем все обработчики
router.include_router(base_router)
router.include_router(commands_router)
router.include_router(callbacks_router)

__all__ = ["router"]

from aiogram import Router

from .base import router as base_router
from .commands import router as commands_router
from .callbacks import router as callbacks_router
from .arrival import router as arrival_router

# Главный роутер
router = Router()

# Подключаем все обработчики
router.include_router(base_router)
router.include_router(commands_router)
router.include_router(callbacks_router)
router.include_router(arrival_router)

__all__ = ["router"]

from .base import router
from . import commands   # импортируем модуль команд (у него свой роутер)
from . import callbacks  # импортируем модуль колбэков (использует общий роутер из base)
from .topics.assortment import router as assortment_router
from .topics.arrival import router as arrival_router
from .topics.preorder import router as preorder_router
from .topics.sales import router as sales_router

# Подключаем роутер команд (так как у commands собственный роутер)
router.include_router(commands.router)

# Подключаем роутеры топиков
router.include_router(assortment_router)
router.include_router(arrival_router)
router.include_router(preorder_router)
router.include_router(sales_router)

# Модуль callbacks уже зарегистрировал свои хендлеры на router из base,
# поэтому дополнительно подключать не нужно.

__all__ = ['router']

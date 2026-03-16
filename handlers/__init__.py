from .base import router  # основной роутер, на нем уже висят хендлеры из base

# Импортируем модули, чтобы их хендлеры зарегистрировались
from . import commands   # у commands свой роутер, его нужно подключить через include_router
from . import callbacks  # у callbacks хендлеры висят на router из base, поэтому просто импорт

# Подключаем роутер команд (если у commands свой роутер)
router.include_router(commands.router)

# Подключаем роутеры топиков
from .topics.assortment import router as assortment_router
from .topics.arrival import router as arrival_router
from .topics.preorder import router as preorder_router
from .topics.sales import router as sales_router

router.include_router(assortment_router)
router.include_router(arrival_router)
router.include_router(preorder_router)
router.include_router(sales_router)

# Экспортируем только основной роутер для диспетчера
__all__ = ['router']

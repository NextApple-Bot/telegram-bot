from .base import router
from . import commands
from . import callbacks
from .topics.assortment import router as assortment_router
from .topics.arrival import router as arrival_router
from .topics.preorder import router as preorder_router
from .topics.sales import router as sales_router
from .debug import debug_router

# ... (существующие подключения)

# Подключаем временный роутер (после основных, но можно в любом месте)
router.include_router(debug_router)
# Включаем роутеры топиков в основной
router.include_router(assortment_router)
router.include_router(arrival_router)
router.include_router(preorder_router)
router.include_router(sales_router)

# Если нужно экспортировать что-то ещё
__all__ = ['router']

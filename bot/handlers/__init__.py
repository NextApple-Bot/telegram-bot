from .base import router
from . import commands
from . import callbacks
from .topics import assortment_router, arrival_router, preorder_router, sales_router

router.include_router(commands.router)
router.include_router(callbacks.router)  # если у callbacks есть свой роутер, но в нашем коде он использует base.router, поэтому можно не подключать
router.include_router(assortment_router)
router.include_router(arrival_router)
router.include_router(preorder_router)
router.include_router(sales_router)

__all__ = ['router']

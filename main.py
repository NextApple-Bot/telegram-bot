import asyncio
import logging
import os
import signal
import sys
import time
import traceback

import uvicorn
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text
from starlette.applications import Starlette
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

# ... (весь остальной код остаётся без изменений до строки с import routers)

# === ИСПРАВЛЕНИЕ: подключаем все topic-роутеры ===
from bot.handlers.topics import (
    arrival_router,
    assortment_router,
    preorder_router,
    sales_router,
)

# ... (в initialize, после создания dp)

        from bot.handlers import router
        self.dp.include_router(router)
        self.dp.include_router(sales_router)
        self.dp.include_router(preorder_router)
        self.dp.include_router(arrival_router)
        self.dp.include_router(assortment_router)
        logger.info("✅ Все topic-роутеры подключены")

# ... (остальной код без изменений)
# Файл: web_admin/routes/debug.py
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from bot.db import get_pool
from bot.services.cache import cache
import os
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/debug")
async def debug_info(request: Request):
    # Простейшая защита: проверяем, что пользователь авторизован в админке
    if not request.session.get("authenticated"):
        raise HTTPException(status_code=403, detail="Forbidden")

    pool = await get_pool()
    db_connections = 0
    try:
        async with pool.acquire() as conn:
            # Примерное количество активных соединений (может не поддерживаться)
            row = await conn.fetchrow("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
            db_connections = row[0] if row else "unknown"
    except Exception as e:
        logger.error(f"Ошибка при получении статистики БД: {e}")
        db_connections = "error"

    redis_status = "not configured"
    if cache._enabled:
        try:
            await cache._redis.ping()
            redis_status = "healthy"
        except Exception as e:
            redis_status = f"unhealthy: {e}"

    app_version = os.getenv("APP_VERSION", "unknown")
    last_errors = []  # Можно читать из лог-файла, но пока опустим

    return JSONResponse({
        "database": {
            "active_connections": db_connections
        },
        "redis": redis_status,
        "app_version": app_version,
        "last_errors": last_errors
    })

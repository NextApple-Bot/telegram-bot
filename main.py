import asyncio
import logging
import os
import signal
import sys
import time

import uvicorn
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

from prometheus_fastapi_instrumentator import Instrumentator

# ====================== SENTRY ======================
SENTRY_DSN = os.getenv("SENTRY_DSN")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
    from sentry_sdk.integrations.starlette import StarletteIntegration
    from sentry_sdk.integrations.fastapi import FastApiIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=1.0,
        environment=os.getenv("ENVIRONMENT", "production"),
        integrations=[StarletteIntegration(), FastApiIntegration()],
    )
    logging.info("✅ Sentry инициализирован")
else:
    logging.info("ℹ️ SENTRY_DSN не задан, мониторинг ошибок отключён")

# ====================== LOGGING ======================
log_format = os.getenv("LOG_FORMAT", "text").lower()
if log_format == "json":
    from pythonjsonlogger import jsonlogger
    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter('%(asctime)s %(name)s %(levelname)s %(message)s')
    handler.setFormatter(formatter)
    logging.getLogger().handlers = [handler]
    logging.getLogger().setLevel(logging.INFO)
else:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

logger = logging.getLogger(__name__)


class HealthCheckFilter(logging.Filter):
    def filter(self, record):
        return not (hasattr(record, 'message') and '/health' in record.getMessage())


logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())
load_dotenv()


class Application:
    def __init__(self):
        self.bot = None
        self.dp = None
        self.config = None
        self._redis_client = None

    async def initialize(self):
        from bot.config import config
        from bot.db import get_async_session_factory, dispose_engine
        from bot.middleware.error_handler import ErrorHandlerMiddleware
        from aiogram import Bot, Dispatcher
        from aiogram.fsm.storage.memory import MemoryStorage
        import redis.asyncio as redis
        from aiogram.fsm.storage.redis import RedisStorage

        self.config = config
        logger.info("✅ Конфигурация загружена")

        # Bot
        self.bot = Bot(token=config.BOT_TOKEN)
        logger.info("✅ Экземпляр Bot создан")

        # Storage
        if config.REDIS_URL:
            self._redis_client = redis.from_url(config.REDIS_URL, decode_responses=True)
            storage = RedisStorage(redis=self._redis_client)
            logger.info("✅ RedisStorage для FSM")
        else:
            storage = MemoryStorage()
            logger.warning("⚠️ MemoryStorage (без Redis)")

        self.dp = Dispatcher(storage=storage)
        self.dp.update.middleware(ErrorHandlerMiddleware())
        logger.info("✅ Диспетчер создан")

        # Роутеры
        from bot.handlers import router
        self.dp.include_router(router)
        logger.info("✅ Роутер подключён")

        # Проверка доступа к БД (создаст движок, если нужно)
        async_session = get_async_session_factory()
        async with async_session() as session:
            await session.execute("SELECT 1")
        logger.info("✅ Подключение к БД подтверждено")

        # Фоновые задачи
        from bot.background import start_background_tasks
        asyncio.create_task(start_background_tasks(self.bot, self.dp))
        logger.info("✅ Фоновые задачи запущены")

        # Вебхук
        await self._setup_webhook()
        return self

    async def _setup_webhook(self, max_retries=5, base_delay=3):
        if not self.config.RENDER_URL:
            logger.error("❌ RENDER_URL не задан — вебхук не будет установлен.")
            return
        webhook_url = f"{self.config.RENDER_URL}/webhook"
        for attempt in range(1, max_retries + 1):
            try:
                await self.bot.delete_webhook(drop_pending_updates=True)
                allowed_updates = self.dp.resolve_used_update_types()
                await self.bot.set_webhook(url=webhook_url, allowed_updates=allowed_updates)
                logger.info(f"✅ Вебхук установлен на {webhook_url} (попытка {attempt})")
                return
            except Exception as e:
                logger.warning(f"⚠️ Попытка {attempt}/{max_retries} не удалась: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(base_delay * attempt)
                else:
                    logger.error(f"❌ Не удалось установить вебхук после {max_retries} попыток")

    async def shutdown(self):
        logger.info("🛑 Завершение работы...")
        if self.bot:
            try:
                await self.bot.delete_webhook()
                await self.bot.session.close()
                logger.info("✅ Бот закрыт")
            except Exception as e:
                logger.error(f"Ошибка при закрытии бота: {e}")
        if self._redis_client:
            await self._redis_client.aclose()
            logger.info("✅ Redis-клиент закрыт")
        from bot.db import dispose_engine
        await dispose_engine()
        logger.info("✅ Пул БД закрыт")


# ─── HTTP handlers ──────────────────────────────────────
async def webhook(request: Request, app: Application) -> Response:
    if not app.bot or not app.dp:
        return Response(status_code=503)
    try:
        from aiogram.types import Update
        update_data = await request.json()
        update = Update(**update_data)
        await app.dp.feed_update(app.bot, update)
        return Response(status_code=200)
    except Exception:
        logger.exception("❌ Ошибка обработки вебхука")
        return Response(status_code=500)


async def health(_: Request) -> Response:
    from bot.db import check_db_health, check_redis_health
    db_ok = await check_db_health()
    redis_ok = await check_redis_health()
    # Telegram проверка не делается для быстроты, всегда OK
    if db_ok and redis_ok:
        return PlainTextResponse("OK")
    status = {}
    if not db_ok:
        status["database"] = "unhealthy"
    if not redis_ok:
        status["redis"] = "unhealthy"
    return JSONResponse(status, status_code=503)


async def health_detailed(_: Request) -> Response:
    from bot.db import check_db_health, check_redis_health
    start = time.monotonic()
    db_ok = await check_db_health()
    db_time = time.monotonic() - start
    start = time.monotonic()
    redis_ok = await check_redis_health()
    redis_time = time.monotonic() - start
    telegram_ok = True
    telegram_time = None
    # Можно добавить проверку Telegram API, если есть бот
    overall = db_ok and redis_ok and telegram_ok
    return JSONResponse({
        "status": "healthy" if overall else "unhealthy",
        "database": {"status": "up" if db_ok else "down", "response_time_ms": round(db_time*1000, 2) if db_ok else None},
        "redis": {"status": "up" if redis_ok else "down", "response_time_ms": round(redis_time*1000, 2) if redis_ok else None},
        "telegram_api": {"status": "up" if telegram_ok else "down", "response_time_ms": round(telegram_time*1000, 2) if telegram_ok and telegram_time else None}
    }, status_code=200 if overall else 503)


def create_starlette_app(app_instance):
    routes = [
        Route("/webhook", lambda req: webhook(req, app_instance), methods=["POST"]),
        Route("/health", health, methods=["GET"]),
        Route("/health/detailed", health_detailed, methods=["GET"]),
    ]
    starlette_app = Starlette(routes=routes, on_startup=[lambda: None], on_shutdown=[lambda: None])

    # Prometheus
    Instrumentator().instrument(starlette_app).expose(starlette_app, endpoint="/metrics")

    # Sentry
    if SENTRY_DSN:
        starlette_app = SentryAsgiMiddleware(starlette_app)

    # SessionMiddleware & админка
    if app_instance.config.SECRET_KEY:
        starlette_app.add_middleware(SessionMiddleware, secret_key=app_instance.config.SECRET_KEY)
        logger.info("✅ SessionMiddleware добавлена")
    else:
        logger.warning("⚠️ SECRET_KEY не задан")

    if app_instance.config.ADMIN_PASSWORD and app_instance.config.SECRET_KEY:
        try:
            from web_admin.main import app as admin_app
            starlette_app.mount("/admin", admin_app)
            logger.info("✅ Веб-админка смонтирована на /admin")
        except Exception as e:
            logger.error(f"❌ Не удалось смонтировать веб-админку: {e}")
    else:
        logger.info("ℹ️ Веб-админка не настроена")

    return starlette_app


async def main():
    app = Application()
    try:
        await app.initialize()
    except Exception:
        logger.critical("Не удалось инициализировать приложение")
        sys.exit(1)

    starlette_app = create_starlette_app(app)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(app.shutdown()))

    port = int(os.getenv("PORT", "8000"))
    logger.info(f"🚀 Запуск сервера на порту {port}")
    config = uvicorn.Config(
        starlette_app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        timeout_graceful_shutdown=30,
        timeout_keep_alive=30
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())

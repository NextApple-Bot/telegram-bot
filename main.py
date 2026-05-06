import asyncio
import logging
import os
import signal
import sys
import time

import uvicorn
from dotenv import load_dotenv

# Prometheus
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.applications import Starlette
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

# Sentry (если настроен)
SENTRY_DSN = os.getenv("SENTRY_DSN")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=1.0,
        environment=os.getenv("ENVIRONMENT", "production"),
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
        ],
    )
    logging.info("✅ Sentry инициализирован")
else:
    logging.info("ℹ️ SENTRY_DSN не задан, мониторинг ошибок отключён")

# Настройка логирования
log_format = os.getenv("LOG_FORMAT", "text").lower()
if log_format == "json":
    from pythonjsonlogger import jsonlogger
    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter('%(asctime)s %(name)s %(levelname)s %(message)s')
    handler.setFormatter(formatter)
    logging.getLogger().handlers = [handler]
    logging.getLogger().setLevel(logging.INFO)
else:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

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
        self._pool = None

    async def initialize(self):
        """Инициализация всех компонентов (бот, диспетчер, БД)."""
        import redis.asyncio as redis
        from aiogram import Bot, Dispatcher
        from aiogram.fsm.storage.memory import MemoryStorage
        from aiogram.fsm.storage.redis import RedisStorage

        from bot import config as bot_config
        from bot.db import get_pool, init_db

        self.config = bot_config
        logger.info("✅ Конфигурация загружена")

        # Проверка масштабирования
        scaling_enabled = os.getenv("SCALING_ENABLED", "false").lower() == "true"
        if scaling_enabled and not self.config.REDIS_URL:
            logger.critical("❌ SCALING_ENABLED=True, но REDIS_URL не задан.")
            sys.exit(1)

        # Bot
        self.bot = Bot(token=self.config.TOKEN)
        logger.info("✅ Экземпляр Bot создан")

        # Storage и Dispatcher
        if self.config.REDIS_URL:
            redis_client = redis.from_url(self.config.REDIS_URL, decode_responses=True)
            storage = RedisStorage(redis=redis_client)
            logger.info("✅ Используется RedisStorage для FSM")
        else:
            if scaling_enabled:
                logger.critical("❌ Масштабирование требует RedisStorage.")
                sys.exit(1)
            storage = MemoryStorage()
            logger.warning("⚠️ REDIS_URL не задан, используется MemoryStorage")

        self.dp = Dispatcher(storage=storage)
        logger.info("✅ Диспетчер создан")

        # Подключаем роутеры
        from bot.handlers import router
        if router.parent_router is None:
            self.dp.include_router(router)
            logger.info("✅ Роутер подключён")
        else:
            logger.warning("⚠️ Роутер уже прикреплён к другому диспетчеру, пропускаем")

        # Инициализация БД
        try:
            self._pool = await get_pool()
            logger.info("✅ Пул соединений БД инициализирован")
            await init_db()
            logger.info("✅ Инициализация БД выполнена")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации пула БД: {e}")
            raise

        # Фоновые задачи
        from bot.background import start_background_tasks
        asyncio.create_task(start_background_tasks(self.bot, self.dp))
        logger.info("✅ Фоновые задачи запущены")

        # Установка вебхука
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
        """Корректное завершение работы."""
        logger.info("🛑 Завершение работы...")
        if self.bot:
            try:
                await self.bot.delete_webhook()
                await self.bot.session.close()
                logger.info("✅ Вебхук удалён, сессия бота закрыта")
            except Exception as e:
                logger.error(f"Ошибка при закрытии бота: {e}")
        if self.dp and hasattr(self.dp.storage, 'redis') and self.dp.storage.redis:
            try:
                await self.dp.storage.redis.aclose()
                logger.info("✅ Redis-клиент закрыт")
            except Exception as e:
                logger.error(f"Ошибка при закрытии Redis: {e}")
        if self._pool:
            await self._pool.close()
            logger.info("✅ Пул БД закрыт")

    # --- HTTP обработчики ---
    async def webhook(self, request: Request) -> Response:
        if not self.bot or not self.dp:
            return Response(status_code=503)
        try:
            from aiogram.types import Update
            update_data = await request.json()
            update = Update(**update_data)
            await self.dp.feed_update(self.bot, update)
            return Response(status_code=200)
        except Exception:
            logger.exception("❌ Ошибка обработки вебхука")
            return Response(status_code=500)

    async def health(self, _: Request) -> Response:
        from bot.db import check_db_health, check_redis_health
        db_ok = await check_db_health()
        redis_ok = await check_redis_health()
        telegram_ok = True
        if self.bot:
            try:
                await self.bot.get_me()
            except Exception as e:
                logger.warning(f"Telegram health check failed: {e}")
                telegram_ok = False
        if db_ok and redis_ok and telegram_ok:
            return PlainTextResponse("OK")
        status = {}
        if not db_ok:
            status["database"] = "unhealthy"
        if not redis_ok:
            status["redis"] = "unhealthy"
        if not telegram_ok:
            status["telegram"] = "unhealthy"
        return JSONResponse(status, status_code=503)

    async def health_detailed(self, _: Request) -> Response:
        from bot.db import check_db_health, check_redis_health
        start = time.monotonic()
        db_ok = await check_db_health()
        db_time = time.monotonic() - start
        start = time.monotonic()
        redis_ok = await check_redis_health()
        redis_time = time.monotonic() - start
        telegram_ok = True
        telegram_time = None
        if self.bot:
            start = time.monotonic()
            try:
                await self.bot.get_me()
                telegram_time = time.monotonic() - start
            except Exception as e:
                logger.warning(f"Detailed Telegram health failed: {e}")
                telegram_ok = False
                telegram_time = time.monotonic() - start
        overall = db_ok and redis_ok and telegram_ok
        return JSONResponse({
            "status": "healthy" if overall else "unhealthy",
            "database": {"status": "up" if db_ok else "down", "response_time_ms": round(db_time*1000, 2) if db_ok else None},
            "redis": {"status": "up" if redis_ok else "down", "response_time_ms": round(redis_time*1000, 2) if redis_ok else None},
            "telegram_api": {"status": "up" if telegram_ok else "down", "response_time_ms": round(telegram_time*1000, 2) if telegram_ok and telegram_time else None}
        }, status_code=200 if overall else 503)


def create_starlette_app(app_instance: Application) -> Starlette:
    """Создаёт Starlette-приложение, используя экземпляр Application."""
    starlette_app = Starlette(
        routes=[
            Route("/webhook", app_instance.webhook, methods=["POST"]),
            Route("/health", app_instance.health, methods=["GET"]),
            Route("/health/detailed", app_instance.health_detailed, methods=["GET"]),
        ],
        on_startup=[lambda: None],   # реальная инициализация делается до запуска
        on_shutdown=[lambda: None],
    )

    # Prometheus
    Instrumentator().instrument(starlette_app).expose(starlette_app, endpoint="/metrics")

    # Sentry ASGI middleware
    if SENTRY_DSN:
        starlette_app = SentryAsgiMiddleware(starlette_app)

    # SessionMiddleware и админка
    if app_instance.config.SECRET_KEY:
        starlette_app.add_middleware(SessionMiddleware, secret_key=app_instance.config.SECRET_KEY)
        logger.info("✅ SessionMiddleware добавлена")
    else:
        logger.warning("⚠️ SECRET_KEY не задан, сессии не будут работать")

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
    # Основной поток инициализации
    app = Application()
    try:
        await app.initialize()
    except Exception:
        logger.critical("Не удалось инициализировать приложение")
        sys.exit(1)

    starlette_app = create_starlette_app(app)

    # Обработка сигналов
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(handle_signal(app, starlette_app))
        )

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


async def handle_signal(app: Application, starlette_app):
    logger.info("Получен сигнал завершения...")
    await app.shutdown()
    # uvicorn сам остановится, но можно дополнительно вызвать shutdown у сервера
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())

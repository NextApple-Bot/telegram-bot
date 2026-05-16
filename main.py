import asyncio
import logging
import os
import signal
import sys
import time
import traceback

import uvicorn
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.applications import Starlette
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

# ==================== Sentry ====================
SENTRY_DSN = os.getenv("SENTRY_DSN")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=0.3,
        environment=os.getenv("ENVIRONMENT", "production"),
        integrations=[StarletteIntegration(), FastApiIntegration()],
    )
    logging.info("✅ Sentry инициализирован")
else:
    logging.info("ℹ️ Sentry отключён")

# ==================== Logging ====================
if os.getenv("LOG_FORMAT", "text").lower() == "json":
    from pythonjsonlogger import jsonlogger
    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(message)s %(pathname)s %(lineno)d'
    )
    handler.setFormatter(formatter)
    logging.getLogger().handlers = [handler]
    logging.getLogger().setLevel(logging.INFO)
else:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

logger = logging.getLogger(__name__)


class Application:
    def __init__(self):
        self.bot = None
        self.dp = None
        self.config = None
        self._redis_client = None

    async def initialize(self):
        import redis.asyncio as redis
        from aiogram import Bot, Dispatcher
        from aiogram.fsm.storage.memory import MemoryStorage
        from aiogram.fsm.storage.redis import RedisStorage

        from bot.config import config as bot_config
        from bot.db import get_async_session_factory, check_db_health   # ← исправлено

        self.config = bot_config
        logger.info("✅ Конфигурация загружена")

        self.bot = Bot(token=bot_config.BOT_TOKEN, parse_mode="HTML")
        logger.info("✅ Bot создан")

        # Storage
        if bot_config.REDIS_URL:
            self._redis_client = redis.from_url(bot_config.REDIS_URL, decode_responses=True)
            storage = RedisStorage(redis=self._redis_client)
            logger.info("✅ RedisStorage")
        else:
            storage = MemoryStorage()
            logger.warning("⚠️ MemoryStorage (dev)")

        self.dp = Dispatcher(storage=storage)
        from bot.middleware.error_handler import ErrorHandlerMiddleware
        self.dp.update.middleware(ErrorHandlerMiddleware())

        from bot.handlers import router
        self.dp.include_router(router)

        # DB check
        if not await check_db_health():
            logger.error("❌ База данных недоступна")
            raise RuntimeError("Database unavailable")

        # Background tasks
        from bot.background import start_background_tasks
        asyncio.create_task(start_background_tasks(self.bot, self.dp))

        await self._setup_webhook()
        return self

    async def _setup_webhook(self, max_retries: int = 5):
        if not self.config.RENDER_URL:
            logger.warning("RENDER_URL не задан → webhook пропущен (локальный режим)")
            return

        webhook_url = f"{self.config.RENDER_URL.rstrip('/')}/webhook"

        for attempt in range(1, max_retries + 1):
            try:
                await self.bot.delete_webhook(drop_pending_updates=True)
                allowed = self.dp.resolve_used_update_types()
                await self.bot.set_webhook(
                    url=webhook_url,
                    allowed_updates=allowed,
                    secret_token=self.config.SECRET_KEY[:32] if self.config.SECRET_KEY else None
                )
                logger.info(f"✅ Webhook установлен: {webhook_url}")
                return
            except Exception as e:
                logger.warning(f"Попытка {attempt}/{max_retries}: {e}")
                await asyncio.sleep(3 * attempt)

        logger.error("❌ Не удалось установить webhook")

    async def shutdown(self):
        logger.info("🛑 Завершение...")
        if self.bot:
            try:
                await self.bot.delete_webhook()
                await self.bot.session.close()
            except Exception as e:
                logger.error(f"Ошибка закрытия бота: {e}")

        if self._redis_client:
            await self._redis_client.aclose()

        from bot.db import close_db
        await close_db()

        logger.info("✅ Приложение остановлено")

    # ... (webhook, health и т.д. — можешь оставить как было)


def create_starlette_app(app_instance: Application):
    routes = [
        Route("/webhook", app_instance.webhook, methods=["POST"]),
        Route("/health", app_instance.health, methods=["GET"]),
        Route("/health/detailed", app_instance.health_detailed, methods=["GET"]),
    ]

    starlette_app = Starlette(routes=routes)
    Instrumentator().instrument(starlette_app).expose(starlette_app, endpoint="/metrics")

    if SENTRY_DSN:
        starlette_app = SentryAsgiMiddleware(starlette_app)

    if app_instance.config.SECRET_KEY:
        starlette_app.add_middleware(
            SessionMiddleware,
            secret_key=app_instance.config.SECRET_KEY,
            https_only=True,
            same_site="lax",
            max_age=60 * 60 * 24 * 7,
        )

    # Монтируем админку
    try:
        from web_admin.main import app as admin_app
        starlette_app.mount("/admin", admin_app)
        logger.info("✅ Админка подключена на /admin")
    except Exception as e:
        logger.error(f"Не удалось подключить админку: {e}")

    return starlette_app


async def main_entry():
    app = Application()
    await app.initialize()

    starlette_app = create_starlette_app(app)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(app.shutdown()))

    port = int(os.getenv("PORT", 8000))
    config = uvicorn.Config(
        starlette_app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        timeout_graceful_shutdown=60,
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main_entry())

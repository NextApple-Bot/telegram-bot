import asyncio
import logging
import os
import signal

import uvicorn
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.applications import Starlette
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
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
        traces_sample_rate=0.5,                    # уменьшил до 50%
        environment=os.getenv("ENVIRONMENT", "production"),
        integrations=[StarletteIntegration(), FastApiIntegration()],
    )
    logging.info("✅ Sentry инициализирован")
else:
    logging.info("ℹ️ Sentry отключён")

# ==================== Logging ====================
log_format = os.getenv("LOG_FORMAT", "text").lower()
if log_format == "json":
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
        from bot.db import check_db_health
        from bot.middleware.error_handler import ErrorHandlerMiddleware

        self.config = bot_config
        logger.info("✅ Конфигурация загружена")

        self.bot = Bot(token=bot_config.BOT_TOKEN, parse_mode="HTML")
        logger.info("✅ Bot создан")

        # ==================== Storage ====================
        if bot_config.REDIS_URL:
            self._redis_client = redis.from_url(bot_config.REDIS_URL, decode_responses=True)
            storage = RedisStorage(redis=self._redis_client)
            logger.info("✅ RedisStorage для FSM")
        else:
            storage = MemoryStorage()
            logger.warning("⚠️ Используется MemoryStorage (без Redis)")

        self.dp = Dispatcher(storage=storage)
        self.dp.update.middleware(ErrorHandlerMiddleware())
        logger.info("✅ Dispatcher создан")

        # Подключаем роутеры
        from bot.handlers import router
        self.dp.include_router(router)

        # Проверка БД
        if not await check_db_health():
            logger.error("❌ Не удалось подключиться к базе данных")
            raise RuntimeError("Database unavailable")
        logger.info("✅ Подключение к БД подтверждено")

        # Фоновые задачи
        from bot.background import start_background_tasks
        asyncio.create_task(start_background_tasks(self.bot, self.dp))

        await self._setup_webhook()
        return self

    async def _setup_webhook(self, max_retries: int = 5):
        if not self.config.RENDER_URL:
            logger.warning("RENDER_URL не задан — webhook не установлен (локальный режим)")
            return

        webhook_url = f"{self.config.RENDER_URL.rstrip('/')}/webhook"

        for attempt in range(1, max_retries + 1):
            try:
                await self.bot.delete_webhook(drop_pending_updates=True)
                allowed_updates = self.dp.resolve_used_update_types()
                await self.bot.set_webhook(
                    url=webhook_url,
                    allowed_updates=allowed_updates,
                    secret_token=self.config.SECRET_KEY[:32] if self.config.SECRET_KEY else None
                )
                logger.info(f"✅ Webhook установлен: {webhook_url}")
                return
            except Exception as e:
                logger.warning(f"Попытка {attempt}/{max_retries} не удалась: {e}")
                await asyncio.sleep(3 * attempt)

        logger.error("❌ Не удалось установить webhook")

    async def shutdown(self):
        logger.info("🛑 Завершение приложения...")
        if self.bot:
            try:
                await self.bot.delete_webhook()
                await self.bot.session.close()
            except Exception as e:
                logger.error(f"Ошибка закрытия бота: {e}")

        if self._redis_client:
            await self._redis_client.aclose()

        from bot.db import dispose_engine
        await dispose_engine()

        logger.info("✅ Приложение остановлено")

    # ==================== Webhook handler ====================
    async def webhook(self, request: Request) -> Response:
        if not self.bot or not self.dp:
            return Response(status_code=503)

        try:
            from aiogram.types import Update
            update = Update.model_validate(await request.json())
            await self.dp.feed_update(self.bot, update)
            return Response(status_code=200)
        except Exception:
            logger.exception("Ошибка в webhook")
            return Response(status_code=500)

    # ==================== Healthchecks ====================
    async def health(self, _: Request) -> Response:
        from bot.db import check_db_health, check_redis_health
        ok = await check_db_health() and await check_redis_health()
        return PlainTextResponse("OK" if ok else "FAIL", status_code=200 if ok else 503)

    async def health_detailed(self, _: Request) -> Response:
        # ... (оставил вашу реализацию, она хорошая)
        ...


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

    # Session middleware
    if app_instance.config.SECRET_KEY:
        starlette_app.add_middleware(
            SessionMiddleware,
            secret_key=app_instance.config.SECRET_KEY,
            https_only=True,
            same_site="lax",
            max_age=60 * 60 * 24 * 7,   # 7 дней
        )

    # Монтируем админку
    if app_instance.config.ADMIN_PASSWORD_HASH and app_instance.config.SECRET_KEY:
        try:
            from web_admin.main import app as admin_app
            starlette_app.mount("/admin", admin_app)
            logger.info("✅ Web Admin Panel mounted on /admin")
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

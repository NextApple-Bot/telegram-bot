import asyncio
import logging
import os
import signal

import uvicorn
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text
from starlette.applications import Starlette
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route

# ==================== Logging ====================
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
        from bot.db import get_async_session_factory, init_db, close_db   # ← исправлено

        self.config = bot_config
        logger.info("✅ Конфигурация загружена")

        # Инициализация БД
        await init_db()
        logger.info("✅ База данных инициализирована")

        self.bot = Bot(token=bot_config.BOT_TOKEN, parse_mode="HTML")
        logger.info("✅ Bot создан")

        # Storage
        if bot_config.REDIS_URL and "redis" in bot_config.REDIS_URL:
            self._redis_client = redis.from_url(bot_config.REDIS_URL, decode_responses=True)
            storage = RedisStorage(redis=self._redis_client)
            logger.info("✅ RedisStorage")
        else:
            storage = MemoryStorage()
            logger.warning("⚠️ MemoryStorage (dev)")

        self.dp = Dispatcher(storage=storage)

        # Middleware
        from bot.middleware.error_handler import ErrorHandlerMiddleware
        self.dp.update.middleware(ErrorHandlerMiddleware())

        # Handlers
        from bot.handlers import router
        self.dp.include_router(router)

        # Background tasks
        from bot.background import start_background_tasks
        asyncio.create_task(start_background_tasks(self.bot, self.dp))

        await self._setup_webhook()
        logger.info("✅ Бот полностью инициализирован")
        return self

    async def _setup_webhook(self, max_retries: int = 5):
        if not getattr(self.config, 'RENDER_URL', None) and not getattr(self.config, 'WEBHOOK_BASE_URL', None):
            logger.warning("RENDER_URL / WEBHOOK_BASE_URL не задан → webhook пропущен")
            return

        base_url = getattr(self.config, 'RENDER_URL', None) or getattr(self.config, 'WEBHOOK_BASE_URL', '')
        webhook_url = f"{base_url.rstrip('/')}/webhook"

        for attempt in range(1, max_retries + 1):
            try:
                await self.bot.delete_webhook(drop_pending_updates=True)
                allowed = self.dp.resolve_used_update_types()
                await self.bot.set_webhook(
                    url=webhook_url,
                    allowed_updates=allowed,
                    secret_token=self.config.SECRET_KEY[:32] if getattr(self.config, 'SECRET_KEY', None) else None
                )
                logger.info(f"✅ Webhook установлен: {webhook_url}")
                return
            except Exception as e:
                logger.warning(f"Webhook attempt {attempt}/{max_retries} failed: {e}")
                await asyncio.sleep(3 * attempt)

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

        from bot.db import close_db
        await close_db()

        logger.info("✅ Приложение остановлено")

    async def webhook(self, request: Request) -> Response:
        if not self.bot or not self.dp:
            return Response(status_code=503)
        try:
            from aiogram.types import Update
            update = Update.model_validate(await request.json())
            await self.dp.feed_update(self.bot, update)
            return Response(status_code=200)
        except Exception as e:
            logger.exception("Ошибка в webhook")
            return Response(status_code=500)

    async def health(self, _: Request) -> Response:
        """Простой healthcheck"""
        try:
            from bot.db import get_async_session_factory
            session_factory = await get_async_session_factory()
            async with session_factory() as session:
                await session.execute(text("SELECT 1"))
            return PlainTextResponse("OK", status_code=200)
        except Exception:
            return PlainTextResponse("FAIL", status_code=503)


def create_starlette_app(app_instance: Application):
    routes = [
        Route("/webhook", app_instance.webhook, methods=["POST"]),
        Route("/health", app_instance.health, methods=["GET"]),
    ]

    starlette_app = Starlette(routes=routes)
    Instrumentator().instrument(starlette_app).expose(starlette_app, endpoint="/metrics")

    if getattr(app_instance.config, 'SECRET_KEY', None):
        starlette_app.add_middleware(
            SessionMiddleware,
            secret_key=app_instance.config.SECRET_KEY,
            https_only=True,
            same_site="lax",
        )

    # Админка
    try:
        from web_admin.main import app as admin_app
        starlette_app.mount("/admin", admin_app)
        logger.info("✅ Админ-панель подключена")
    except Exception as e:
        logger.warning(f"Админка не подключена: {e}")

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

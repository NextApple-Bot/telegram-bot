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
        from aiogram.client.default import DefaultBotProperties   # ← важно!
        from aiogram.fsm.storage.memory import MemoryStorage
        from aiogram.fsm.storage.redis import RedisStorage

        from bot.config import config as bot_config
        from bot.db import init_db, close_db

        self.config = bot_config
        logger.info("✅ Конфигурация загружена")

        await init_db()
        logger.info("✅ База данных инициализирована")

        # ==================== ИСПРАВЛЕНИЕ aiogram 3.7+ ====================
        self.bot = Bot(
            token=bot_config.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode="HTML")
        )
        logger.info("✅ Bot создан (aiogram 3.7+)")

        # Storage
        if bot_config.REDIS_URL and "redis" in bot_config.REDIS_URL.lower():
            self._redis_client = redis.from_url(bot_config.REDIS_URL, decode_responses=True)
            storage = RedisStorage(redis=self._redis_client)
            logger.info("✅ RedisStorage")
        else:
            storage = MemoryStorage()
            logger.warning("⚠️ MemoryStorage (dev)")

        self.dp = Dispatcher(storage=storage)

        # Middleware & Handlers
        from bot.middleware.error_handler import ErrorHandlerMiddleware
        self.dp.update.middleware(ErrorHandlerMiddleware())

        from bot.handlers import router
        self.dp.include_router(router)

        # Background tasks
        from bot.background import start_background_tasks
        asyncio.create_task(start_background_tasks(self.bot, self.dp))

        await self._setup_webhook()
        logger.info("✅ Бот полностью инициализирован")
        return self

    async def _setup_webhook(self, max_retries: int = 5):
        base_url = getattr(self.config, 'RENDER_URL', None) or getattr(self.config, 'WEBHOOK_BASE_URL', None)
        if not base_url:
            logger.warning("Webhook URL не задан → пропускаем")
            return

        webhook_url = f"{base_url.rstrip('/')}/webhook"

        for attempt in range(1, max_retries + 1):
            try:
                await self.bot.delete_webhook(drop_pending_updates=True)
                allowed = self.dp.resolve_used_update_types()
                await self.bot.set_webhook(
                    url=webhook_url,
                    allowed_updates=allowed,
                    secret_token=getattr(self.config, 'SECRET_KEY', None)
                )
                logger.info(f"✅ Webhook установлен: {webhook_url}")
                return
            except Exception as e:
                logger.warning(f"Попытка {attempt}: {e}")
                await asyncio.sleep(3)

    async def shutdown(self):
        logger.info("🛑 Завершение...")
        if self.bot:
            await self.bot.session.close()
        if self._redis_client:
            await self._redis_client.aclose()
        from bot.db import close_db
        await close_db()

    async def webhook(self, request: Request) -> Response:
        try:
            from aiogram.types import Update
            update = Update.model_validate(await request.json())
            await self.dp.feed_update(self.bot, update)
            return Response(status_code=200)
        except Exception as e:
            logger.exception("Webhook error")
            return Response(status_code=500)

    async def health(self, _: Request) -> Response:
        try:
            from bot.db import get_async_engine
            engine = get_async_engine()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return PlainTextResponse("OK")
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
        starlette_app.add_middleware(SessionMiddleware, secret_key=app_instance.config.SECRET_KEY)

    try:
        from web_admin.main import app as admin_app
        starlette_app.mount("/admin", admin_app)
    except Exception as e:
        logger.warning(f"Админка не подключилась: {e}")

    return starlette_app


async def main_entry():
    app = Application()

    # Главное исправление: создаём Starlette приложение СРАЗУ,
    # чтобы /health был доступен до тяжёлой инициализации
    starlette_app = create_starlette_app(app)

    # Теперь запускаем тяжёлую инициализацию (бот, webhook, роутеры и т.д.)
    await app.initialize()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(app.shutdown()))

    port = int(os.getenv("PORT", 8000))
    config = uvicorn.Config(starlette_app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main_entry())

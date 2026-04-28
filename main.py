# Файл: main.py
import sys
import logging
import os
import traceback
import asyncio
import signal
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
import uvicorn
from dotenv import load_dotenv
import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class HealthCheckFilter(logging.Filter):
    def filter(self, record):
        if hasattr(record, 'message') and '/health' in record.getMessage():
            return False
        return True

logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())
load_dotenv()

bot = None
dp = None
config = None

try:
    from aiogram import Bot, Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.fsm.storage.redis import RedisStorage
    from aiogram.types import Update
    from bot.handlers import router
    from bot.db import close_pool, get_pool, init_db, check_db_health, check_redis_health
    from bot import config as bot_config
    import redis.asyncio as redis

    config = bot_config
    logger.info("✅ Конфигурация загружена")

    scaling_enabled = os.getenv("SCALING_ENABLED", "false").lower() == "true"
    if scaling_enabled and not config.REDIS_URL:
        logger.critical("❌ SCALING_ENABLED=True, но REDIS_URL не задан. Масштабирование невозможно.")
        sys.exit(1)

    bot = Bot(token=config.TOKEN)
    logger.info("✅ Экземпляр Bot создан")

    if config.REDIS_URL:
        redis_client = redis.from_url(config.REDIS_URL, decode_responses=True)
        storage = RedisStorage(redis=redis_client)
        logger.info("✅ Используется RedisStorage для FSM")
    else:
        if scaling_enabled:
            logger.critical("❌ Масштабирование требует RedisStorage.")
            sys.exit(1)
        storage = MemoryStorage()
        logger.warning("⚠️ REDIS_URL не задан, используется MemoryStorage")

    dp = Dispatcher(storage=storage)
    logger.info("✅ Диспетчер создан")

    if router.parent_router is None:
        dp.include_router(router)
        logger.info("✅ Роутер подключён")
    else:
        logger.warning("⚠️ Роутер уже прикреплён к другому диспетчеру, пропускаем повторное включение")

except Exception as e:
    logger.error(f"❌ Ошибка при инициализации бота: {e}")
    logger.error(traceback.format_exc())


async def on_startup():
    logger.info("🚀 on_startup: запуск...")
    # ---------- ХИРУРГИЧЕСКИЙ УДАР (ИСПРАВЛЕНО) ----------
    if config and not getattr(config, 'RENDER_URL', None):
        logger.critical("❌ RENDER_URL не задан. Бот не сможет принимать вебхуки. Аварийное завершение.")
        sys.exit(1)
    # ----------------------------------------
    try:
        await get_pool()
        logger.info("✅ Пул соединений БД инициализирован")
        await init_db()
        logger.info("✅ Инициализация БД (таблицы, колонки) выполнена")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации пула БД: {e}")

    from bot.background import start_background_tasks
    asyncio.create_task(start_background_tasks(bot, dp))
    logger.info("✅ Фоновые задачи запущены (с блокировками Redis)")

    if bot and dp:
        logger.info("✅ Бот и диспетчер готовы")
        if config and hasattr(config, 'RENDER_URL') and config.RENDER_URL:
            webhook_url = f"{config.RENDER_URL}/webhook"
            try:
                await bot.delete_webhook(drop_pending_updates=True)
                allowed_updates = dp.resolve_used_update_types()
                await bot.set_webhook(
                    url=webhook_url,
                    allowed_updates=allowed_updates
                )
                logger.info(f"✅ Вебхук установлен на {webhook_url}")
            except Exception as e:
                logger.error(f"❌ Не удалось установить вебхук: {e}")
        else:
            logger.warning("⚠️ RENDER_URL не задан, вебхук не будет установлен")
    else:
        logger.warning("⚠️ Бот не инициализирован, пропускаем установку вебхука")


async def on_shutdown():
    logger.info("🛑 Завершение работы, закрываем пул соединений...")
    try:
        await close_pool()
    except Exception as e:
        logger.error(f"Ошибка при закрытии пула: {e}")
    if bot:
        try:
            await bot.delete_webhook()
            await bot.session.close()
            logger.info("✅ Вебхук удалён, сессия бота закрыта")
        except Exception as e:
            logger.error(f"Ошибка при завершении работы бота: {e}")
    if dp and hasattr(dp.storage, 'redis') and dp.storage.redis:
        try:
            await dp.storage.redis.aclose()
            logger.info("✅ Redis-клиент закрыт")
        except Exception as e:
            logger.error(f"Ошибка при закрытии Redis: {e}")


async def webhook(request: Request) -> Response:
    if not bot or not dp:
        logger.error("❌ Бот не инициализирован, запрос отклонён")
        return Response(status_code=503)
    try:
        update_data = await request.json()
        logger.info(f"📨 Получено обновление: update_id={update_data.get('update_id')}")
        update = Update(**update_data)
        await dp.feed_update(bot, update)
        return Response(status_code=200)
    except Exception as e:
        logger.exception(f"❌ Ошибка при обработке вебхука: {e}")
        return Response(status_code=500)


async def health(_: Request) -> Response:
    db_ok = await check_db_health()
    redis_ok = await check_redis_health()
    telegram_ok = True
    if bot:
        try:
            await bot.get_me()
        except Exception as e:
            logger.warning(f"Telegram API health check failed: {e}")
            telegram_ok = False

    if db_ok and redis_ok and telegram_ok:
        return PlainTextResponse("OK")
    else:
        status = {}
        if not db_ok:
            status["database"] = "unhealthy"
        if not redis_ok:
            status["redis"] = "unhealthy"
        if not telegram_ok:
            status["telegram"] = "unhealthy"
        return JSONResponse(status, status_code=503)


app = Starlette(
    routes=[
        Route("/webhook", webhook, methods=["POST"]),
        Route("/health", health, methods=["GET"]),
    ],
    on_startup=[on_startup],
    on_shutdown=[on_shutdown],
)

if config and config.SECRET_KEY:
    app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY)
    logger.info("✅ SessionMiddleware добавлена")
else:
    logger.warning("⚠️ SECRET_KEY не задан, сессии не будут работать")

if config and config.ADMIN_PASSWORD and config.SECRET_KEY:
    try:
        from web_admin.main import app as admin_app
        app.mount("/admin", admin_app)
        logger.info("✅ Веб-админка смонтирована на /admin")
    except Exception as e:
        logger.error(f"❌ Не удалось смонтировать веб-админку: {e}")
else:
    logger.info("ℹ️ Веб-админка не настроена (отсутствуют ADMIN_PASSWORD или SECRET_KEY)")

def handle_exit_signal(signum, frame):
    logger.info(f"Получен сигнал {signum}, запускаем graceful shutdown...")
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_exit_signal)
signal.signal(signal.SIGINT, handle_exit_signal)

if __name__ == "__main__":
    PORT = int(os.getenv("PORT", 8000))
    logger.info(f"🚀 Запуск сервера на порту {PORT}, интерфейс 0.0.0.0")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level="info",
        timeout_graceful_shutdown=30,
        timeout_keep_alive=30
    )

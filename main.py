# Файл: main.py
import sys
import logging
import os
import traceback
import asyncio
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
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
    from bot.db import close_pool, get_pool, init_db, cleanup_sold_periodically
    from bot import config as bot_config
    import redis.asyncio as redis

    config = bot_config
    logger.info("✅ Конфигурация загружена")

    bot = Bot(token=config.TOKEN)
    logger.info("✅ Экземпляр Bot создан")

    if config.REDIS_URL:
        redis_client = redis.from_url(config.REDIS_URL, decode_responses=True)
        storage = RedisStorage(redis=redis_client)
        logger.info("✅ Используется RedisStorage для FSM")
    else:
        storage = MemoryStorage()
        logger.warning("⚠️ REDIS_URL не задан, используется MemoryStorage")

    dp = Dispatcher(storage=storage)
    logger.info("✅ Диспетчер создан")

    dp.include_router(router)
    logger.info("✅ Роутер подключён")

except Exception as e:
    logger.error(f"❌ Ошибка при инициализации бота: {e}")
    logger.error(traceback.format_exc())


async def check_and_set_webhook():
    """Проверяет текущий вебхук через Telegram API и переустанавливает, если нужно."""
    if not bot or not config or not config.RENDER_URL:
        logger.warning("❌ Нельзя проверить вебхук: бот или RENDER_URL не заданы")
        return

    expected_url = f"{config.RENDER_URL}/webhook"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.telegram.org/bot{config.TOKEN}/getWebhookInfo") as resp:
                data = await resp.json()
                if not data.get("ok"):
                    logger.error(f"Ошибка получения информации о вебхуке: {data}")
                    return
                current_url = data["result"].get("url", "")
                if current_url != expected_url:
                    logger.warning(f"Вебхук не соответствует: ожидается {expected_url}, сейчас {current_url}. Переустанавливаем...")
                    await bot.delete_webhook(drop_pending_updates=True)
                    await bot.set_webhook(
                        url=expected_url,
                        allowed_updates=dp.resolve_used_update_types()
                    )
                    logger.info(f"✅ Вебхук переустановлен на {expected_url}")
                else:
                    logger.debug(f"Вебхук корректен: {expected_url}")
    except Exception as e:
        logger.error(f"Ошибка при проверке вебхука: {e}")


async def webhook_healthcheck():
    """Фоновая задача: проверяет вебхук каждые 5 минут."""
    while True:
        await asyncio.sleep(300)  # 5 минут
        await check_and_set_webhook()


async def on_startup():
    logger.info("🚀 on_startup: запуск...")
    try:
        await get_pool()
        logger.info("✅ Пул соединений БД инициализирован")
        await init_db()
        logger.info("✅ Инициализация БД (таблицы, колонки) выполнена")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации пула БД: {e}")

    asyncio.create_task(cleanup_sold_periodically())
    logger.info("✅ Фоновая задача очистки продаж запущена")

    asyncio.create_task(webhook_healthcheck())
    logger.info("✅ Фоновая задача проверки вебхука запущена (каждые 5 минут)")

    if bot and dp:
        logger.info("✅ Бот и диспетчер готовы")
        if config and hasattr(config, 'RENDER_URL') and config.RENDER_URL:
            webhook_url = f"{config.RENDER_URL}/webhook"
            try:
                await bot.delete_webhook(drop_pending_updates=True)
                await bot.set_webhook(
                    url=webhook_url,
                    allowed_updates=dp.resolve_used_update_types()
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


async def health(_: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")


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

if __name__ == "__main__":
    PORT = int(os.getenv("PORT", 8000))
    logger.info(f"🚀 Запуск сервера на порту {PORT}, интерфейс 0.0.0.0")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")

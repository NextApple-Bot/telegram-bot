import os
import logging
import sys
import traceback
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
import uvicorn
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

try:
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.requests import Request
    from starlette.responses import PlainTextResponse, Response
    import uvicorn
    from dotenv import load_dotenv
    logger.info("✅ Базовые модули импортированы")
except Exception as e:
    logger.critical(f"❌ Ошибка импорта базовых модулей: {e}")
    sys.exit(1)

load_dotenv()

bot = None
dp = None
config = None

try:
    from aiogram import Bot, Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.types import Update
    from bot.handlers import router
    from bot.db import init_db
    from bot import config as bot_config
    config = bot_config

    bot = Bot(token=config.TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    logger.info("✅ Бот и диспетчер созданы")
except Exception as e:
    logger.error(f"❌ Ошибка при инициализации бота: {e}")
    logger.error(traceback.format_exc())
    # не выходим, чтобы сервер хотя бы health check отдавал

async def on_startup():
    logger.info("🚀 on_startup: запуск...")
    if bot and dp:
        try:
            await init_db()
            logger.info("✅ База данных готова")
        except Exception as e:
            logger.error(f"❌ Ошибка при инициализации БД: {e}")

        if config and hasattr(config, 'RENDER_URL') and config.RENDER_URL:
            webhook_url = f"{config.RENDER_URL}/webhook"
            try:
                await bot.delete_webhook(drop_pending_updates=True)
                await bot.set_webhook(url=webhook_url, allowed_updates=dp.resolve_used_update_types())
                logger.info(f"✅ Вебхук установлен на {webhook_url}")
            except Exception as e:
                logger.error(f"❌ Не удалось установить вебхук: {e}")
        else:
            logger.warning("⚠️ RENDER_URL не задан, вебхук не будет установлен")
    else:
        logger.warning("⚠️ Бот не инициализирован, пропускаем установку вебхука и БД")

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
)

if __name__ == "__main__":
    PORT = int(os.getenv("PORT", 8000))
    logger.info(f"🚀 Запуск сервера на порту {PORT}, интерфейс 0.0.0.0")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")

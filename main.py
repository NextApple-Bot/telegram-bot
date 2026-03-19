import os
import logging
import asyncio
import sys
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
import uvicorn
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from aiogram import Bot, Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.types import Update
    from bot.handlers import router
    from bot.db import init_db
    from bot import config
    logger.info("✅ Все модули импортированы")
except Exception as e:
    logger.critical(f"❌ Ошибка импорта: {e}", exc_info=True)
    sys.exit(1)

bot = Bot(token=config.TOKEN)
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(router)

async def on_startup():
    logger.info("🚀 Запуск бота...")
    try:
        await init_db()
        logger.info("✅ База данных готова")
    except Exception as e:
        logger.error(f"❌ Ошибка БД: {e}")

    # Удаляем старый вебхук и устанавливаем новый
    webhook_url = f"{config.RENDER_URL}/webhook"
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(url=webhook_url, allowed_updates=dp.resolve_used_update_types())
    logger.info(f"✅ Вебхук установлен на {webhook_url}")

async def webhook(request: Request) -> Response:
    """Обработчик входящих обновлений от Telegram"""
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
    """Эндпоинт для проверки здоровья (Render требует его для бесплатных сервисов)"""
    return PlainTextResponse("OK")

# Создаём Starlette приложение
app = Starlette(
    routes=[
        Route("/webhook", webhook, methods=["POST"]),
        Route("/health", health, methods=["GET"]),
    ],
    on_startup=[on_startup],
)

if __name__ == "__main__":
    PORT = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=PORT)

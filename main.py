import os
import logging
import signal
import sys
import asyncio
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from aiogram.fsm.storage.memory import MemoryStorage

import config
import handlers

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=config.TOKEN)
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(handlers.router)

RENDER_URL = os.environ.get('RENDER_EXTERNAL_URL')
PORT = int(os.environ.get('PORT', 8000))

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        logger.info(f"➡️ Входящий запрос: {request.method} {request.url.path}")
        try:
            response = await call_next(request)
            logger.info(f"⬅️ Ответ: {response.status_code}")
            return response
        except Exception as e:
            logger.exception(f"💥 Необработанное исключение при обработке запроса {request.url.path}: {e}")
            return Response(status_code=500)

async def setup_webhook(retries=3):
    logger.info(f"🌐 RENDER_EXTERNAL_URL = {RENDER_URL}")
    if not RENDER_URL:
        logger.error("❌ RENDER_EXTERNAL_URL не задан! Вебхук не будет установлен.")
        return False
    webhook_url = f"{RENDER_URL}/webhook"
    for attempt in range(1, retries+1):
        logger.info(f"🔗 Попытка {attempt} установить вебхук на {webhook_url}")
        try:
            result = await bot.set_webhook(
                url=webhook_url,
                allowed_updates=dp.resolve_used_update_types(),
                drop_pending_updates=True
            )
            logger.info(f"📦 Результат set_webhook: {result}")
            if result:
                webhook_info = await bot.get_webhook_info()
                logger.info(f"🔍 Текущий вебхук: {webhook_info.url}")
                if webhook_info.url == webhook_url:
                    logger.info(f"✅ Вебхук успешно установлен и подтверждён на {webhook_url}")
                    return True
                else:
                    logger.warning(f"⚠️ URL вебхука не совпадает: {webhook_info.url} != {webhook_url}")
            else:
                logger.warning(f"⚠️ Попытка {attempt}: set_webhook вернул False")
        except Exception as e:
            logger.exception(f"❌ Ошибка при установке вебхука (попытка {attempt}): {e}")
        if attempt < retries:
            wait = 2 ** attempt
            logger.info(f"⏳ Повтор через {wait} секунд...")
            await asyncio.sleep(wait)
    logger.error("❌ Не удалось установить вебхук после нескольких попыток.")
    return False

async def on_startup():
    await setup_webhook()

async def on_shutdown():
    logger.info("🗑️ Удаляем вебхук...")
    try:
        await bot.delete_webhook()
        logger.info("✅ Вебхук удалён")
    except Exception as e:
        logger.exception(f"❌ Ошибка при удалении вебхука: {e}")
    await dp.storage.close()
    await bot.session.close()

async def webhook(request: Request) -> Response:
    try:
        update_data = await request.json()
        logger.info(f"📨 Получено обновление от Telegram: update_id={update_data.get('update_id')}")
        update = Update(**update_data)
        await dp.feed_update(bot, update)
        return Response(status_code=200)
    except Exception as e:
        logger.exception(f"❌ Ошибка при обработке вебхука: {e}")
        return Response(status_code=500)

async def health(request: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")

app = Starlette(
    routes=[
        Route("/webhook", webhook, methods=["POST"]),
        Route("/health", health, methods=["GET"]),
        Route("/", health, methods=["GET"]),
    ],
    on_startup=[on_startup],
    on_shutdown=[on_shutdown],
)

app.add_middleware(LoggingMiddleware)

def handle_signal(sig, frame):
    logger.info(f"⏹️ Получен сигнал {sig}, завершаем работу...")
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    try:
        logger.info(f"🚀 Запуск сервера на порту {PORT}")
        uvicorn.run(app, host="0.0.0.0", port=PORT)
    except Exception as e:
        logger.exception(f"💥 Критическая ошибка при запуске: {e}")
        sys.exit(1)
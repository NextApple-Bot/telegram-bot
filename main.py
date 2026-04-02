# Файл: main.py
import sys
import logging
import os
import signal
import asyncio
import traceback
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.middleware.sessions import SessionMiddleware
import uvicorn
from dotenv import load_dotenv

# Настройка базового логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Фильтр для /health
class HealthCheckFilter(logging.Filter):
    def filter(self, record):
        if hasattr(record, 'message') and '/health' in record.getMessage():
            return False
        return True

logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())
load_dotenv()

# Глобальные переменные
bot = None
dp = None
config = None
shutdown_event = asyncio.Event()

# Импортируем модули бота
try:
    from aiogram import Bot, Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.types import Update
    from bot.handlers import router
    from bot.db import close_pool, get_pool, cleanup_old_records
    from bot import config as bot_config

    config = bot_config
    logger.info("✅ Конфигурация загружена")

    bot = Bot(token=config.TOKEN)
    logger.info("✅ Экземпляр Bot создан")

    dp = Dispatcher(storage=MemoryStorage())
    logger.info("✅ Диспетчер создан")

    dp.include_router(router)
    logger.info("✅ Роутер подключён")

except Exception as e:
    logger.error(f"❌ Ошибка при инициализации бота: {e}")
    logger.error(traceback.format_exc())


# Генерация секрета для вебхука (если не задан в .env)
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
if not WEBHOOK_SECRET:
    import secrets
    WEBHOOK_SECRET = secrets.token_urlsafe(32)
    logger.warning(f"⚠️ WEBHOOK_SECRET не задан, сгенерирован временный: {WEBHOOK_SECRET}")
    logger.warning("Рекомендуется добавить WEBHOOK_SECRET в .env для постоянства")


async def on_startup():
    logger.info("🚀 on_startup: запуск...")
    
    # Принудительно создаём пул соединений
    try:
        await get_pool()
        logger.info("✅ Пул соединений БД инициализирован")
        # Запускаем фоновую очистку старых записей
        asyncio.create_task(cleanup_old_records())
        logger.info("✅ Фоновая задача очистки БД запущена")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации пула БД: {e}")
    
    if bot and dp:
        logger.info("✅ Бот и диспетчер готовы")
        if config and hasattr(config, 'RENDER_URL') and config.RENDER_URL:
            webhook_url = f"{config.RENDER_URL}/webhook"
            try:
                await bot.delete_webhook(drop_pending_updates=True)
                # Устанавливаем вебхук с секретным токеном
                await bot.set_webhook(
                    url=webhook_url,
                    secret_token=WEBHOOK_SECRET,
                    allowed_updates=dp.resolve_used_update_types()
                )
                logger.info(f"✅ Вебхук установлен на {webhook_url} с секретным токеном")
            except Exception as e:
                logger.error(f"❌ Не удалось установить вебхук: {e}")
        else:
            logger.warning("⚠️ RENDER_URL не задан, вебхук не будет установлен")
    else:
        logger.warning("⚠️ Бот не инициализирован, пропускаем установку вебхука")


async def on_shutdown():
    logger.info("🛑 Завершение работы, закрываем пул соединений...")
    await close_pool()
    if bot:
        try:
            await bot.delete_webhook()
            await bot.session.close()
            logger.info("✅ Вебхук удалён, сессия бота закрыта")
        except Exception as e:
            logger.error(f"Ошибка при завершении работы бота: {e}")


async def webhook(request: Request) -> Response:
    # Проверка секретного токена
    received_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not received_token or received_token != WEBHOOK_SECRET:
        logger.warning(f"Неверный или отсутствующий секретный токен вебхука")
        return Response(status_code=403)
    
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


def handle_sigterm(*args):
    """Обработчик SIGTERM для graceful shutdown."""
    logger.info("Получен сигнал SIGTERM, завершаем работу...")
    shutdown_event.set()


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

# Монтируем веб-админку
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
    # Регистрируем обработчик сигналов
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)
    
    logger.info(f"🚀 Запуск сервера на порту {PORT}, интерфейс 0.0.0.0")
    # Запускаем uvicorn с обработкой сигналов
    config_uvicorn = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info")
    server = uvicorn.Server(config_uvicorn)
    
    # Запускаем сервер в отдельной задаче
    loop = asyncio.get_event_loop()
    server_task = loop.create_task(server.serve())
    
    # Ждём сигнал завершения
    try:
        await shutdown_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        # Останавливаем uvicorn сервер
        server.should_exit = True
        await server_task
        logger.info("Сервер остановлен")

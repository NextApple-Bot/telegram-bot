import os
import logging
import asyncio
import sys
from dotenv import load_dotenv

# Загружаем .env файл
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from aiogram import Bot, Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage
    from bot.handlers import router
    from bot.db import init_db
    import config
    logger.info("✅ Все модули импортированы")
except Exception as e:
    logger.critical(f"❌ Ошибка импорта: {e}", exc_info=True)
    sys.exit(1)

async def main():
    """Основная функция запуска бота"""
    logger.info("🚀 Запуск бота...")
    
    # Инициализация БД
    try:
        await init_db()
        logger.info("✅ База данных готова")
    except Exception as e:
        logger.error(f"❌ Ошибка БД: {e}")
        # Продолжаем работу? Решайте сами
        # Можно выйти: sys.exit(1)
    
    # Создаём бота и диспетчер
    bot = Bot(token=config.TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    
    logger.info(f"🤖 Бот запущен и слушает обновления")
    logger.info(f"👤 Администраторы: {config.ADMIN_IDS}")
    
    # Запускаем long polling
    try:
        await dp.start_polling(bot)
    finally:
        # Закрываем соединения при остановке
        await bot.session.close()
        logger.info("👋 Бот остановлен")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен пользователем")
    except Exception as e:
        logger.critical(f"💥 Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)

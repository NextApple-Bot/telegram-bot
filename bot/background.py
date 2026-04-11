# Файл: bot/background.py
import asyncio
import logging
from datetime import datetime, timedelta
from bot.db import get_pool
from bot.services.cache import cache
from bot import config

logger = logging.getLogger(__name__)

# Константы для блокировок в Redis
CLEANUP_LOCK_KEY = "background:cleanup_old_records:lock"
CLEANUP_SOLD_LOCK_KEY = "background:cleanup_sold:lock"
LOCK_TTL = 86400 * 2  # 2 дня, чтобы точно пережить сутки


async def cleanup_old_records():
    """Удаляет старые записи из processed_messages и daily_payments."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            res1 = await conn.execute('DELETE FROM processed_messages WHERE processed_at < NOW() - INTERVAL \'30 days\'')
            res2 = await conn.execute('DELETE FROM daily_payments WHERE created_at < NOW() - INTERVAL \'90 days\'')
            logger.info(f"Очистка БД: удалено processed_messages={res1.split()[1] if res1.startswith('DELETE') else 0}, daily_payments={res2.split()[1] if res2.startswith('DELETE') else 0}")
    except Exception as e:
        logger.exception(f"Ошибка при фоновой очистке БД: {e}")


async def cleanup_sold_periodically():
    """Удаляет записи о проданных товарах старше 7 дней."""
    try:
        pool = await get_pool()
        cutoff = datetime.now() - timedelta(days=7)
        async with pool.acquire() as conn:
            result = await conn.execute("DELETE FROM deleted_items WHERE reason = 'sale_from_admin' AND deleted_at < $1", cutoff)
            deleted = result.split()[1] if result.startswith('DELETE') else 0
            logger.info(f"Очистка продаж: удалено {deleted} записей старше 7 дней")
    except Exception as e:
        logger.exception(f"Ошибка при очистке продаж: {e}")


async def run_with_lock(lock_key: str, task_func, ttl: int = LOCK_TTL):
    """
    Выполняет задачу только если удалось захватить блокировку в Redis.
    Если блокировка не захвачена, значит задача уже выполняется на другой реплике.
    """
    if not config.REDIS_URL:
        # Если Redis не настроен, выполняем задачу без блокировки (риск дублирования при масштабировании)
        logger.warning(f"Redis не настроен, выполняем {task_func.__name__} без блокировки")
        await task_func()
        return

    # Пытаемся установить блокировку с помощью SET NX
    redis_client = cache._redis
    acquired = await redis_client.set(lock_key, "locked", nx=True, ex=ttl)
    if acquired:
        logger.info(f"Блокировка {lock_key} захвачена, выполняем {task_func.__name__}")
        try:
            await task_func()
        finally:
            await redis_client.delete(lock_key)
            logger.info(f"Блокировка {lock_key} освобождена")
    else:
        logger.info(f"Блокировка {lock_key} уже захвачена, пропускаем выполнение {task_func.__name__}")


async def background_cleanup_loop():
    """Цикл очистки старых записей (раз в сутки)."""
    while True:
        await asyncio.sleep(86400)
        await run_with_lock(CLEANUP_LOCK_KEY, cleanup_old_records)


async def background_sold_cleanup_loop():
    """Цикл очистки проданных товаров (раз в сутки)."""
    while True:
        await asyncio.sleep(86400)
        await run_with_lock(CLEANUP_SOLD_LOCK_KEY, cleanup_sold_periodically)


async def webhook_healthcheck_loop():
    """Проверка вебхука каждые 5 минут (без блокировки, т.к. не критично дублирование)."""
    from main import check_and_set_webhook
    while True:
        await asyncio.sleep(300)
        await check_and_set_webhook()


async def start_background_tasks():
    """Запускает все фоновые задачи."""
    asyncio.create_task(background_cleanup_loop())
    asyncio.create_task(background_sold_cleanup_loop())
    asyncio.create_task(webhook_healthcheck_loop())
    logger.info("Все фоновые задачи запущены")

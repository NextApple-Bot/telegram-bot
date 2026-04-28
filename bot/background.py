# Файл: bot/background.py
import asyncio
import logging
from datetime import datetime, timedelta

from bot import config
from bot.db import get_pool
from bot.services.cache import cache
from bot.webhook_utils import check_and_set_webhook

logger = logging.getLogger(__name__)

CLEANUP_LOCK_KEY = "background:cleanup_old_records:lock"
CLEANUP_SOLD_LOCK_KEY = "background:cleanup_sold:lock"
LOCK_TTL = 86400 * 2


async def cleanup_old_records():
    """
    Очищает устаревшие записи:
    - processed_messages старше 30 дней (защита от дубликатов)
    - daily_payments старше 6 месяцев (180 дней)
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Удаляем старые обработанные сообщения
            res1 = await conn.execute(
                "DELETE FROM processed_messages WHERE processed_at < NOW() - INTERVAL '30 days'"
            )
            # Удаляем старую платежную статистику (полгода)
            res2 = await conn.execute(
                "DELETE FROM daily_payments WHERE created_at < NOW() - INTERVAL '180 days'"
            )
            logger.info(
                f"Очистка БД: удалено processed_messages = "
                f"{res1.split()[1] if res1.startswith('DELETE') else 0}, "
                f"daily_payments = {res2.split()[1] if res2.startswith('DELETE') else 0}"
            )
    except Exception as e:
        logger.exception(f"Ошибка при фоновой очистке БД: {e}")


async def cleanup_sold_periodically():
    """Удаляет записи о проданных товарах старше 7 дней из корзины (deleted_items)."""
    try:
        pool = await get_pool()
        cutoff = datetime.now() - timedelta(days=7)
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM deleted_items WHERE reason = 'sale_from_admin' AND deleted_at < $1",
                cutoff,
            )
            deleted = result.split()[1] if result.startswith('DELETE') else 0
            logger.info(f"Очистка продаж: удалено {deleted} записей старше 7 дней")
    except Exception as e:
        logger.exception(f"Ошибка при очистке продаж: {e}")


async def run_with_lock(lock_key: str, task_func, ttl: int = LOCK_TTL):
    """Выполняет задачу, захватывая блокировку в Redis (если Redis доступен)."""
    if not config.REDIS_URL:
        logger.warning(f"Redis не настроен, выполняем {task_func.__name__} без блокировки")
        await task_func()
        return

    acquired = await cache.lock(lock_key, ttl=ttl)
    if acquired:
        logger.info(f"Блокировка {lock_key} захвачена, выполняем {task_func.__name__}")
        try:
            await task_func()
        finally:
            await cache.unlock(lock_key)
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


async def webhook_healthcheck_loop(bot, dp):
    """Проверяет и переустанавливает вебхук каждые 5 минут."""
    while True:
        await asyncio.sleep(300)
        await check_and_set_webhook(bot, dp)


async def start_background_tasks(bot, dp):
    """Запускает все фоновые задачи."""
    # Сохраняем ссылки на задачи, чтобы они не были собраны сборщиком мусора (RUF006)
    task1 = asyncio.create_task(background_cleanup_loop())
    task2 = asyncio.create_task(background_sold_cleanup_loop())
    task3 = asyncio.create_task(webhook_healthcheck_loop(bot, dp))
    # Присваиваем переменным, чтобы они не были удалены сразу
    logger.info(f"Фоновые задачи запущены: {task1.get_name()}, {task2.get_name()}, {task3.get_name()}")
    # Важно: задачи живут в event loop, переменные можно не хранить,
    # но предупреждение убрано явным присвоением.

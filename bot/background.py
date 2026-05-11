import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import text

from bot.config import config
from bot.db import get_async_session_factory
from bot.services.cache import cache

logger = logging.getLogger(__name__)

CLEANUP_LOCK_KEY = "background:cleanup_old_records:lock"
CLEANUP_SOLD_LOCK_KEY = "background:cleanup_sold:lock"
LOCK_TTL = 86400 * 2


async def cleanup_old_records():
    try:
        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            r1 = await session.execute(text("DELETE FROM processed_messages WHERE processed_at < NOW() - INTERVAL '30 days'"))
            r2 = await session.execute(text("DELETE FROM daily_payments WHERE created_at < NOW() - INTERVAL '180 days'"))
            logger.info(f"Очистка: processed_messages={r1.rowcount}, daily_payments={r2.rowcount}")
    except Exception as e:
        logger.exception(f"Ошибка очистки: {e}")


async def cleanup_sold_periodically():
    try:
        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            cutoff = datetime.now() - timedelta(days=7)
            r = await session.execute(text("DELETE FROM deleted_items WHERE reason = 'sale_from_admin' AND deleted_at < :cutoff"), {"cutoff": cutoff})
            logger.info(f"Очистка проданных: удалено {r.rowcount} записей")
    except Exception as e:
        logger.exception(f"Ошибка очистки проданных: {e}")


async def run_with_lock(lock_key: str, task_func, ttl: int = LOCK_TTL):
    if not config.REDIS_URL:
        await task_func()
        return
    acquired = await cache.lock(lock_key, ttl=ttl)
    if acquired:
        try:
            await task_func()
        finally:
            await cache.unlock(lock_key)
    else:
        logger.info(f"Блокировка {lock_key} уже захвачена")


async def background_cleanup_loop():
    while True:
        await asyncio.sleep(86400)
        await run_with_lock(CLEANUP_LOCK_KEY, cleanup_old_records)


async def background_sold_cleanup_loop():
    while True:
        await asyncio.sleep(86400)
        await run_with_lock(CLEANUP_SOLD_LOCK_KEY, cleanup_sold_periodically)


async def webhook_healthcheck_loop(bot, dp):
    from bot.webhook_utils import check_and_set_webhook
    while True:
        await asyncio.sleep(300)
        await check_and_set_webhook(bot, dp)


async def start_background_tasks(bot, dp):
    asyncio.create_task(background_cleanup_loop())
    asyncio.create_task(background_sold_cleanup_loop())
    asyncio.create_task(webhook_healthcheck_loop(bot, dp))
    logger.info("Фоновые задачи запущены")

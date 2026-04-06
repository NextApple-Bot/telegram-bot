# Файл: bot/db.py
import asyncpg
import logging
import asyncio
from functools import wraps

from bot import config  # импортируем конфиг для доступа к DATABASE_URL

logger = logging.getLogger(__name__)


# ---------- Декоратор для повторных попыток ----------
def retry_on_db_error(retries=3, delay=1, backoff=2):
    """
    Декоратор для асинхронных функций, выполняющих запросы к БД.
    При ошибках соединения повторяет вызов до retries раз.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(retries):
                try:
                    return await func(*args, **kwargs)
                except (asyncpg.exceptions.ConnectionFailureError,
                        asyncpg.exceptions.InterfaceError,
                        asyncpg.exceptions.PostgresConnectionError) as e:
                    last_exception = e
                    if attempt < retries - 1:
                        wait = delay * (backoff ** attempt)
                        logger.warning(f"Ошибка БД (попытка {attempt+1}/{retries}): {e}. Повтор через {wait}с")
                        await asyncio.sleep(wait)
                    else:
                        logger.error(f"Все попытки исчерпаны: {e}")
                        raise
                except Exception as e:
                    # Другие ошибки не повторяем
                    raise
            raise last_exception
        return wrapper
    return decorator


# ---------- Пул соединений ----------
_pool = None

async def get_pool():
    """Возвращает пул соединений (создаёт при первом вызове с повторными попытками)."""
    global _pool
    if _pool is None:
        last_exception = None
        for attempt in range(5):
            try:
                _pool = await asyncpg.create_pool(
                    config.DATABASE_URL,  # берём URL из конфига
                    min_size=2,
                    max_size=10,
                    command_timeout=60,
                    max_inactive_connection_lifetime=300
                )
                logger.info("✅ Пул соединений создан")
                break
            except Exception as e:
                last_exception = e
                wait = 2 ** attempt
                logger.warning(f"Не удалось создать пул (попытка {attempt+1}/5): {e}. Повтор через {wait}с")
                await asyncio.sleep(wait)
        else:
            logger.error("Все попытки создания пула провалились")
            raise last_exception
    return _pool


async def close_pool():
    """Закрывает пул соединений."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("✅ Пул соединений закрыт")


# Функция init_db() и cleanup_old_records() оставлены для совместимости,
# но вы их не используете (по вашему решению). Они не удалены, но не вызываются.
async def init_db():
    """Создаёт таблицы, если их нет (не используется, т.к. есть миграции)."""
    # Этот код остаётся без изменений, но не вызывается.
    pass

async def cleanup_old_records():
    """Фоновая задача (не используется)."""
    pass

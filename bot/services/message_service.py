# Файл: bot/services/message_service.py
import logging
from typing import Optional
from aiogram.types import Message, ReactionTypeEmoji
from aiogram.exceptions import TelegramBadRequest
from bot.db import get_pool

logger = logging.getLogger(__name__)


async def is_message_processed(chat_id: int, message_id: int) -> bool:
    """
    Атомарно проверяет, было ли сообщение обработано.
    Использует INSERT ... ON CONFLICT DO NOTHING RETURNING 1,
    чтобы гарантировать однократную обработку даже при гонках.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO processed_messages (chat_id, message_id)
            VALUES ($1, $2)
            ON CONFLICT (chat_id, message_id) DO NOTHING
            RETURNING 1
            """,
            chat_id, message_id
        )
        # Если строка возвращена, значит вставка прошла успешно (сообщение не было обработано)
        return row is None


async def mark_message_processed(chat_id: int, message_id: int) -> bool:
    """
    Помечает сообщение как обработанное и возвращает True, если это первая обработка.
    Атомарно: если сообщение уже было в таблице, вернёт False.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO processed_messages (chat_id, message_id)
            VALUES ($1, $2)
            ON CONFLICT (chat_id, message_id) DO NOTHING
            RETURNING 1
            """,
            chat_id, message_id
        )
        return row is not None


async def safe_react(message: Message, emoji: str) -> None:
    """Безопасно ставит реакцию на сообщение, игнорируя ошибки прав."""
    try:
        await message.react([ReactionTypeEmoji(emoji=emoji)])
    except TelegramBadRequest as e:
        if "REACTION_INVALID" in str(e) or "MESSAGE_REACTIONS_FORBIDDEN" in str(e):
            logger.warning(f"Не удалось поставить реакцию {emoji}: {e}")
        else:
            raise

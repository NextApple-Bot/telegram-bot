# Файл: bot/services/message_service.py
import logging
from aiogram.types import Message, ReactionTypeEmoji
from aiogram.exceptions import TelegramBadRequest
from bot.db import get_pool

logger = logging.getLogger(__name__)


async def is_message_processed(chat_id: int, message_id: int) -> bool:
    """Проверяет, было ли сообщение уже обработано ботом."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT 1 FROM processed_messages WHERE chat_id = $1 AND message_id = $2',
            chat_id, message_id
        )
        return row is not None


async def mark_message_processed(chat_id: int, message_id: int) -> None:
    """Помечает сообщение как обработанное."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            'INSERT INTO processed_messages (chat_id, message_id) VALUES ($1, $2) ON CONFLICT DO NOTHING',
            chat_id, message_id
        )


async def safe_react(message: Message, emoji: str) -> None:
    """Безопасно ставит реакцию на сообщение, игнорируя ошибки прав."""
    try:
        await message.react([ReactionTypeEmoji(emoji=emoji)])
    except TelegramBadRequest as e:
        if "REACTION_INVALID" in str(e) or "MESSAGE_REACTIONS_FORBIDDEN" in str(e):
            logger.warning(f"Не удалось поставить реакцию {emoji}: {e}")
        else:
            raise

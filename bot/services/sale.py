import logging
from bot.repositories import ItemRepository, ClientRepository, StatsRepository, FinanceRepository
from bot.models import ClientData
from bot.utils.validators import extract_serials
from bot.utils.parser import parse_client_data, extract_payment_amounts
from bot.db import get_pool

logger = logging.getLogger(__name__)

class SaleService:
    @staticmethod
    async def is_message_processed(chat_id: int, message_id: int) -> bool:
        """Проверяет, было ли сообщение уже обработано (идемпотентность)."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT 1 FROM processed_messages WHERE chat_id = $1 AND message_id = $2',
                chat_id, message_id
            )
            return row is not None

    @staticmethod
    async def mark_message_processed(chat_id: int, message_id: int):
        """Помечает сообщение как обработанное."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'INSERT INTO processed_messages (chat_id, message_id) VALUES ($1, $2) ON CONFLICT DO NOTHING',
                chat_id, message_id
            )

    @staticmethod
    async def process_sale(content: str, chat_id: int, message_id: int) -> dict:
        """Обрабатывает продажу: уда

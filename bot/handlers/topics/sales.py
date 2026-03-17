import logging
from aiogram import F, Router
from aiogram.types import Message, ReactionTypeEmoji

import config
from bot.services.sale import SaleService
from bot.repositories import StatsRepository
from bot.db import get_pool

logger = logging.getLogger(__name__)
router = Router()

# Таблица для идемпотентности (обработанные сообщения)
async def is_message_processed(chat_id: int, message_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT 1 FROM processed_messages WHERE chat_id = $1 AND message_id = $2', chat_id, message_id)
        return row is not None

async def mark_message_processed(chat_id: int, message_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('INSERT INTO processed_messages (chat_id, message_id) VALUES ($1, $2) ON CONFLICT DO NOTHING', chat_id, message_id)

@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_SALES,
    (F.text | F.caption)
)
async def handle_sales_message(message: Message):
    content = message.text or message.caption
    if not content:
        return

    # Проверка на дубликат
    if await is_message_processed(message.chat.id, message.message_id):
        logger.info(f"Сообщение {message.message_id} уже обработано, пропускаем.")
        return

    try:
        result = await SaleService.process_sale(content, message.chat.id, message.message_id)

        # Если были продажи или оплаты – ставим реакцию
        if result["sold_items"] or any(result["payments"].values()):
            await message.react([ReactionTypeEmoji(emoji='🔥')])

        # Если есть ненайденные серийники – сообщаем
        if result["not_found"]:
            text = "❌ Серийные номера не найдены в ассортименте:\n" + "\n".join(result["not_found"])
            await message.reply(text)

        # Помечаем сообщение как обработанное
        await mark_message_processed(message.chat.id, message.message_id)

    except Exception as e:
        logger.exception(f"Ошибка при обработке продажи: {e}")
        await message.reply("❌ Произошла внутренняя ошибка при обработке продажи.")

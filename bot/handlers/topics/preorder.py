import re
import logging
from aiogram import F, Router
from aiogram.types import Message, ReactionTypeEmoji

from bot import config
from bot.services.booking import BookingService
from bot.repositories import StatsRepository, FinanceRepository
from bot.utils.parser import extract_payment_amounts, extract_prepayments
from bot.db import get_pool

logger = logging.getLogger(__name__)
router = Router()

async def is_message_processed(chat_id: int, message_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT 1 FROM processed_messages WHERE chat_id = $1 AND message_id = $2',
            chat_id, message_id
        )
        return row is not None

async def mark_message_processed(chat_id: int, message_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            'INSERT INTO processed_messages (chat_id, message_id) VALUES ($1, $2) ON CONFLICT DO NOTHING',
            chat_id, message_id
        )

@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_PREORDER,
    (F.text | F.caption)
)
async def handle_preorder(message: Message):
    content = message.text or message.caption
    if not content:
        return

    # Идемпотентность
    if await is_message_processed(message.chat.id, message.message_id):
        logger.info(f"Сообщение {message.message_id} уже обработано, пропускаем.")
        return

    lines = content.strip().splitlines()
    logger.info(f"Получено сообщение в предзаказе, строк: {len(lines)}")

    # Определяем блоки "Бронь:"
    booking_indices = [i for i, line in enumerate(lines) if re.match(r'^бронь\s*:?$', line.strip().lower())]
    logger.info(f"Найдены индексы блоков брони: {booking_indices}")

    if booking_indices:
        # Предзаказ с бронями
        # Обрабатываем предварительную часть (до первой брони) как обычный предзаказ
        preorder_lines = lines[:booking_indices[0]]
        if preorder_lines:
            payments = extract_prepayments('\n'.join(preorder_lines))
            logger.info(f"Предзаказ (до брони): платежи {payments}")
            if any(payments.values()):
                await StatsRepository.add_preorder(**payments)
                await FinanceRepository.add_payments(**payments)
                await message.react([ReactionTypeEmoji(emoji='👌')])
            else:
                logger.info("Нет платежей в предзаказе, реакция не ставится")

        # Обрабатываем каждый блок брони (здесь платежи могут быть как предоплата, так и полная оплата)
        for idx in booking_indices:
            start = idx + 1
            end = booking_indices[booking_indices.index(idx) + 1] if booking_indices.index(idx) + 1 < len(booking_indices) else len(lines)
            booking_lines = lines[start:end]

            result = await BookingService.process_booking(booking_lines)

            if not result.get("success"):
                if result.get("reason") == "no_items":
                    await message.react([ReactionTypeEmoji(emoji='👎')])
                    await message.reply("❌ В блоке брони нет товаров с серийными номерами.")
                else:
                    logger.warning(f"Ошибка обработки брони: {result}")
                continue

            await message.react([ReactionTypeEmoji(emoji='👍')])
            booked_count = len(result.get("results", []))
            await message.reply(f"✅ Добавлена бронь на {booked_count} товаров.")
    else:
        # Обычный предзаказ без броней – учитываем только предоплату
        payments = extract_prepayments(content)
        logger.info(f"Предзаказ без броней: платежи {payments}")
        if any(payments.values()):
            await StatsRepository.add_preorder(**payments)
            await FinanceRepository.add_payments(**payments)
            await message.react([ReactionTypeEmoji(emoji='👌')])
        else:
            logger.info("Нет платежей, пропускаем.")

    # Помечаем сообщение как обработанное
    await mark_message_processed(message.chat.id, message.message_id)

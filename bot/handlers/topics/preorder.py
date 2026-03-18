import re
import logging
from aiogram import F, Router
from aiogram.types import Message, ReactionTypeEmoji

import config
from bot.services.booking import BookingService
from bot.services.assortment import AssortmentService
from bot.repositories import StatsRepository
from bot.utils.parser import extract_payment_amounts

logger = logging.getLogger(__name__)
router = Router()

@router.message(F.chat.id == config.MAIN_GROUP_ID)
async def debug_all_messages(message: Message):
    logger.info(f"🔥 DEBUG: Получено сообщение в группе. Текст: {message.text}")
    logger.info(f"Thread ID: {message.message_thread_id}")
    await message.reply(f"DEBUG: сообщение получено (thread_id={message.message_thread_id})")

@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_PREORDER,
    (F.text | F.caption)
)
async def handle_preorder(message: Message):
    content = message.text or message.caption
    if not content:
        return

    lines = content.strip().splitlines()
    logger.info(f"Получено сообщение, строк: {len(lines)}")

    # Определяем, есть ли в сообщении блоки "Бронь:"
    booking_indices = [i for i, line in enumerate(lines) if re.match(r'^бронь\s*:?$', line.strip().lower())]
    logger.info(f"Найдены индексы блоков брони: {booking_indices}")

    if booking_indices:
        # Есть брони – обрабатываем предварительную часть (до первой брони) как предзаказ
        preorder_lines = lines[:booking_indices[0]]
        if preorder_lines:
            payments = extract_payment_amounts('\n'.join(preorder_lines), ignore_prepay=False)
            logger.info(f"Предзаказ (до брони): платежи {payments}")
            await StatsRepository.add_preorder(**payments)
            await message.react([ReactionTypeEmoji(emoji='👌')])

        # Обрабатываем каждый блок брони
        for idx in booking_indices:
            start = idx + 1
            end = booking_indices[booking_indices.index(idx) + 1] if booking_indices.index(idx) + 1 < len(booking_indices) else len(lines)
            booking_lines = lines[start:end]

            result = await BookingService.process_booking(booking_lines)

            if not result.get("success"):
                if result.get("reason") == "no_items":
                    await message.react([ReactionTypeEmoji(emoji='👎')])
                continue

            # Ставим реакцию и отвечаем
            await message.react([ReactionTypeEmoji(emoji='👍')])
            # Можно добавить детальный ответ, но для краткости просто подтверждение
            await message.reply(f"✅ Добавлена бронь на {len(result['results'])} товаров.")
    else:
        # Обычный предзаказ без броней
        payments = extract_payment_amounts(content, ignore_prepay=False)
        logger.info(f"Предзаказ без броней: платежи {payments}")
        await StatsRepository.add_preorder(**payments)
        await message.react([ReactionTypeEmoji(emoji='👌')])

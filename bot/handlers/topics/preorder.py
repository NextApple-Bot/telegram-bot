import re
import logging
from aiogram import F, Router
from aiogram.types import Message, ReactionTypeEmoji

import config
from bot.services.booking import BookingService
from bot.repositories import StatsRepository, FinanceRepository
from bot.utils.parser import extract_payment_amounts

logger = logging.getLogger(__name__)
router = Router()

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
    logger.info(f"Получено сообщение в предзаказе, строк: {len(lines)}")

    # Определяем, есть ли в сообщении блоки "Бронь:"
    booking_indices = [i for i, line in enumerate(lines) if re.match(r'^бронь\s*:?$', line.strip().lower())]
    logger.info(f"Найдены индексы блоков брони: {booking_indices}")

    # Если есть брони – обрабатываем их, иначе – обычный предзаказ
    if booking_indices:
        # Обрабатываем предварительную часть (до первой брони) как предзаказ
        preorder_lines = lines[:booking_indices[0]]
        if preorder_lines:
            payments = extract_payment_amounts('\n'.join(preorder_lines), ignore_prepay=False)
            logger.info(f"Предзаказ (до брони): платежи {payments}")
            if any(payments.values()):
                await StatsRepository.add_preorder(**payments)
                await FinanceRepository.add_payments(**payments)
                await message.react([ReactionTypeEmoji(emoji='👌')])
            else:
                logger.info("Нет платежей в предзаказе, реакция не ставится")

        # Обрабатываем каждый блок брони
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

            # Ставим реакцию и отвечаем
            await message.react([ReactionTypeEmoji(emoji='👍')])
            booked_count = len(result.get("results", []))
            await message.reply(f"✅ Добавлена бронь на {booked_count} товаров.")
    else:
        # Обычный предзаказ без броней
        payments = extract_payment_amounts(content, ignore_prepay=False)
        logger.info(f"Предзаказ без броней: платежи {payments}")
        if any(payments.values()):
            await StatsRepository.add_preorder(**payments)
            await FinanceRepository.add_payments(**payments)
            await message.react([ReactionTypeEmoji(emoji='👌')])
        else:
            logger.info("Нет платежей, пропускаем.")

# Файл: bot/handlers/topics/preorder.py
import logging
import re
from aiogram import F, Router
from aiogram.types import Message

from bot import config
from bot.services.booking import BookingService
from bot.services.payment import PaymentService
from bot.repositories import StatsRepository, ClientRepository
from bot.utils.parser import extract_prepayments, parse_client_data, extract_payment_amounts
from bot.utils.helpers import send_and_clean
from bot.services.message_service import mark_message_processed, safe_react

logger = logging.getLogger(__name__)
router = Router()


@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_PREORDER,
    (F.text | F.caption)
)
async def handle_preorder(message: Message):
    logger.info(f"[PREORDER] >>> Получено сообщение {message.message_id} в топик предзаказов")

    content = message.text or message.caption
    if not content:
        return

    is_first = await mark_message_processed(message.chat.id, message.message_id)
    if not is_first:
        logger.info(f"[PREORDER] Сообщение {message.message_id} уже обработано — пропускаем")
        return

    lines = content.strip().splitlines()
    booking_indices = [i for i, line in enumerate(lines) if re.match(r'^бронь\s*:?$', line.strip().lower())]

    if booking_indices:
        logger.info(f"[PREORDER] Найдено {len(booking_indices)} блоков 'бронь'")
        # ... остальная логика остаётся без изменений ...
    else:
        logger.info("[PREORDER] Блоков 'бронь' нет — обрабатываем как обычный предзаказ")
        # ... остальная логика ...

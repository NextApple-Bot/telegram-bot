# bot/handlers/topics/sales.py
import logging
import re
from aiogram import F, Router
from aiogram.types import Message

from bot import config
from bot.services.sale import SaleService
from bot.services.payment_parser import extract_payment_amounts
from bot.utils.helpers import send_and_clean
from bot.services.message_service import mark_message_processed

logger = logging.getLogger(__name__)
router = Router()

TRADE_IN_PATTERNS = [r'trade\s*in', r'трейд\s*ин', r'trade\-in']

def remove_trade_in_lines(text: str) -> str:
    lines = text.splitlines()
    return '\n'.join(line for line in lines if not any(re.search(p, line, re.IGNORECASE) for p in TRADE_IN_PATTERNS))


@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_SALES,
    (F.text | F.caption)
)
async def handle_sales_message(message: Message):
    logger.info(f"[SALES] >>> Получено сообщение {message.message_id} в топик продаж")

    content = message.text or message.caption or ""
    if not content.strip():
        logger.warning("[SALES] Пустое сообщение — пропускаем")
        return

    # Проверка на дубликат
    is_first = await mark_message_processed(message.chat.id, message.message_id)
    if not is_first:
        logger.info(f"[SALES] Сообщение {message.message_id} уже обработано — пропускаем")
        return

    cleaned_content = remove_trade_in_lines(content)
    payments = extract_payment_amounts(cleaned_content, ignore_prepay=True)

    logger.info(f"[SALES] Платежи: {payments}")

    if not any(payments.values()):
        logger.info("[SALES] Платежи не найдены — пропускаем")
        return

    try:
        result = await SaleService.process_sale(
            content=cleaned_content,
            chat_id=message.chat.id,
            message_id=message.message_id,
            payments=payments
        )
        logger.info(f"[SALES] Результат: {result}")
    except Exception as e:
        logger.exception("[SALES] Ошибка при обработке продажи")

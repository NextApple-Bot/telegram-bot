# bot/handlers/topics/sales.py
import logging
from aiogram import F, Router
from aiogram.types import Message

from bot import config
from bot.services.sale import SaleService
from bot.services.payment_parser import extract_payment_amounts
from bot.utils.helpers import remove_trade_in_lines, send_and_clean

logger = logging.getLogger(__name__)
router = Router()


@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_SALES,
    (F.text | F.caption)
)
async def handle_sales_message(message: Message):
    """
    Обработчик сообщений о продажах в соответствующем топике
    """
    logger.info(f"[SALES] Получено сообщение {message.message_id} в топик продаж")

    content = message.text or message.caption or ""
    if not content.strip():
        logger.debug("[SALES] Пустое сообщение, пропускаем")
        return

    # Очистка от строк Trade-in
    cleaned_content = remove_trade_in_lines(content)

    # Извлечение сумм платежей
    payments = extract_payment_amounts(cleaned_content, ignore_prepay=True)
    logger.info(f"[SALES] Извлечены платежи: {payments}")

    if not any(payments.values()):
        logger.info("[SALES] Платежи не найдены, пропускаем")
        return

    try:
        result = await SaleService.process_sale(
            content=cleaned_content,
            chat_id=message.chat.id,
            message_id=message.message_id,
            payments=payments
        )

        logger.info(f"[SALES] Результат обработки: {result}")

        if result.get("sold_items"):
            await send_and_clean(
                bot=message.bot,
                chat_id=message.chat.id,
                text=f"Продажа обработана: {len(result['sold_items'])} товар(ов)",
                reply_to_message_id=message.message_id,
                message_thread_id=config.THREAD_SALES,
                delete_after=120
            )
        elif result.get("not_found"):
            await send_and_clean(
                bot=message.bot,
                chat_id=message.chat.id,
                text=f"Не найдены серийные номера: {result['not_found']}",
                reply_to_message_id=message.message_id,
                message_thread_id=config.THREAD_SALES,
                delete_after=120
            )

    except Exception as e:
        logger.exception("[SALES] Критическая ошибка при обработке продажи")
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text="Ошибка при обработке продажи. Администратор уведомлён.",
            reply_to_message_id=message.message_id,
            message_thread_id=config.THREAD_SALES,
            delete_after=120
        )


@router.edited_message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_SALES
)
async def handle_edited_sales(message: Message):
    logger.info(f"[SALES] Отредактировано сообщение {message.message_id}")
    pass
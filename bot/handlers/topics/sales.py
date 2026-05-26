# bot/handlers/topics/sales.py
# Полная версия с восстановленной логикой из v21

import logging
from aiogram import F, Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot import config
from bot.services.sale_service import SaleService
from bot.utils.payment_parser import extract_payment_amounts
from bot.utils.helpers import remove_trade_in_lines, send_and_clean

logger = logging.getLogger(__name__)
router = Router()


@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_SALES,
    (F.text | F.caption)
)
async def handle_sales_message(message: Message, state: FSMContext):
    """
    Основной обработчик продаж в топике Продажи
    """
    content = message.text or message.caption or ""
    if not content.strip():
        return

    # Очистка от строк Trade-in
    cleaned_content = remove_trade_in_lines(content)

    # Извлечение сумм платежей
    payments = extract_payment_amounts(cleaned_content, ignore_prepay=True)

    if not payments:
        # Если платежей не найдено — возможно это служебное сообщение
        logger.debug("В сообщении не найдено сумм платежей")
        return

    try:
        result = await SaleService.process_sale(
            message=message,
            content=cleaned_content,
            payments=payments,
            state=state
        )

        if result.get("success"):
            sale_id = result.get("sale_id")
            await send_and_clean(
                bot=message.bot,
                chat_id=message.chat.id,
                text=f"✅ Продажа успешно обработана!\nID: `{sale_id}`",
                reply_to_message_id=message.message_id,
                message_thread_id=config.THREAD_SALES,
                delete_after=180
            )
        else:
            error_text = result.get("error", "Неизвестная ошибка при обработке продажи")
            await send_and_clean(
                bot=message.bot,
                chat_id=message.chat.id,
                text=f"⚠️ {error_text}",
                reply_to_message_id=message.message_id,
                message_thread_id=config.THREAD_SALES,
                delete_after=120
            )

    except Exception as e:
        logger.exception("Критическая ошибка в обработке продажи")
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text="❌ Произошла ошибка при обработке продажи. Администратор уведомлён.",
            reply_to_message_id=message.message_id,
            message_thread_id=config.THREAD_SALES,
            delete_after=120
        )


# Опционально: можно добавить обработчик для редактирования сообщений о продажах
@router.edited_message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_SALES
)
async def handle_edited_sales(message: Message):
    """Обработка редактирования сообщений в топике продаж"""
    logger.info(f"Отредактировано сообщение о продаже: {message.message_id}")
    # При необходимости можно добавить логику пересчёта продажи
    pass

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
    logger.info(f"[PREORDER] Получено сообщение {message.message_id}")

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
        # === Блок предзаказа перед "бронь" ===
        preorder_lines = lines[:booking_indices[0]]
        if preorder_lines:
            payments = extract_prepayments('\n'.join(preorder_lines))
            if any(payments.values()):
                try:
                    data = parse_client_data('\n'.join(preorder_lines))
                    if data.get('phones') or data.get('full_name'):
                        await ClientRepository.get_or_create_client(
                            phone=data.get('main_phone'),
                            phones=data.get('phones'),
                            full_name=data.get('full_name'),
                            telegram_username=data.get('telegram_username'),
                            social_network=data.get('social_network'),
                            referral_source=data.get('referral_source')
                        )
                except Exception as e:
                    logger.exception("[PREORDER] Ошибка при сохранении клиента (предзаказ)")

                await StatsRepository.add_preorder(**payments)
                await PaymentService.add_payments_batch(payments, source_type='preorder')
                await safe_react(message, '👌')

        # === Обработка блоков "бронь" ===
        for idx in booking_indices:
            start = idx + 1
            end = booking_indices[booking_indices.index(idx) + 1] if booking_indices.index(idx) + 1 < len(booking_indices) else len(lines)
            booking_lines = lines[start:end]
            booking_payments = extract_payment_amounts('\n'.join(booking_lines), ignore_prepay=False)

            result = await BookingService.process_booking(booking_lines, booking_payments)

            if not result.get("success"):
                if result.get("reason") == "no_items":
                    await safe_react(message, '⚠️')
                    await send_and_clean(
                        bot=message.bot,
                        chat_id=message.chat.id,
                        text="В блоке брони нет товаров с серийными номерами.",
                        reply_to_message_id=message.message_id,
                        message_thread_id=config.THREAD_PREORDER,
                        delete_after=60
                    )
                continue

            await safe_react(message, '👍')
            booked_count = len(result.get("results", []))
            await send_and_clean(
                bot=message.bot,
                chat_id=message.chat.id,
                text=f"Добавлена бронь на {booked_count} товаров.",
                reply_to_message_id=message.message_id,
                message_thread_id=config.THREAD_PREORDER,
                delete_after=60
            )
    else:
        # === Обычный предзаказ без блока "бронь" ===
        payments = extract_prepayments(content)
        if any(payments.values()):
            try:
                data = parse_client_data(content)
                if data.get('phones') or data.get('full_name'):
                    await ClientRepository.get_or_create_client(
                        phone=data.get('main_phone'),
                        phones=data.get('phones'),
                        full_name=data.get('full_name'),
                        telegram_username=data.get('telegram_username'),
                        social_network=data.get('social_network'),
                        referral_source=data.get('referral_source')
                    )
            except Exception as e:
                logger.exception("[PREORDER] Ошибка при сохранении клиента")

            await StatsRepository.add_preorder(**payments)
            await PaymentService.add_payments_batch(payments, source_type='preorder')
            await safe_react(message, '👌')

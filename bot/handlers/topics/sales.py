# Файл: bot/handlers/topics/sales.py
import re
import logging
from aiogram import F, Router
from aiogram.types import Message, ReactionTypeEmoji

from bot import config
from bot.services.sale import SaleService
from bot.services.payment import PaymentService
from bot.repositories import ClientRepository
from bot.utils.parser import parse_client_data, extract_payment_amounts
from bot.db import get_pool

logger = logging.getLogger(__name__)
router = Router()

TRADE_IN_PATTERNS = [
    r'trade\s*in',
    r'трейд\s*ин',
    r'trade\-in',
]


def remove_trade_in_lines(text: str) -> str:
    lines = text.splitlines()
    filtered = []
    for line in lines:
        if any(re.search(p, line, re.IGNORECASE) for p in TRADE_IN_PATTERNS):
            continue
        filtered.append(line)
    return '\n'.join(filtered)


@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_SALES,
    (F.text | F.caption)
)
async def handle_sales_message(message: Message):
    content = message.text or message.caption
    if not content:
        return

    if await SaleService.is_message_processed(message.chat.id, message.message_id):
        logger.info(f"Сообщение {message.message_id} уже обработано, пропускаем.")
        return

    content = remove_trade_in_lines(content)
    # Извлекаем платежи один раз
    payments = extract_payment_amounts(content, ignore_prepay=True)
    result = await SaleService.process_sale(content, message.chat.id, message.message_id, payments)

    # Сохранение клиента (только если есть данные)
    try:
        data = parse_client_data(content)
        if data['phones'] or data['full_name']:
            await ClientRepository.get_or_create_client(
                phone=data['main_phone'],
                phones=data['phones'],
                full_name=data['full_name'],
                telegram_username=data['telegram_username'],
                social_network=data['social_network'],
                referral_source=data['referral_source']
            )
    except Exception as e:
        logger.exception(f"Ошибка при сохранении клиента: {e}")

    # Сохраняем платежи, если это не запрещено (skip_payments = True только при ненайденных серийниках)
    if not result.get("skip_payments", False):
        await PaymentService.add_payments_batch(payments, source_type='sale')
        logger.info(f"💰 Платежи сохранены: {payments}")

    # Реакция и сообщения об ошибках
    if result.get("is_accessory"):
        # Аксессуар – только платежи сохранены, статистики продаж нет
        await message.react([ReactionTypeEmoji(emoji='💸')])
        logger.info("Аксессуар: платежи сохранены, статистика продаж не изменена.")
    elif result.get("sold_items"):
        # Продажа товаров с серийниками
        await message.react([ReactionTypeEmoji(emoji='🔥')])
        logger.info(f"✅ Продажа: {len(result['sold_items'])} товаров, статистика и платежи сохранены.")
    elif result.get("not_found"):
        # Серийные номера указаны, но не найдены
        await message.react([ReactionTypeEmoji(emoji='❌')])
        text = "❌ Серийные номера не найдены в ассортименте:\n" + "\n".join(result["not_found"])
        await message.reply(text)
        logger.info("Серийные номера не найдены – ничего не сохранено.")
    else:
        # Прочие случаи (например, дубль сообщения)
        logger.info("Сообщение уже обработано или нет действий.")

    await SaleService.mark_message_processed(message.chat.id, message.message_id)

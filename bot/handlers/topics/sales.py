import re
import logging
from aiogram import F, Router
from aiogram.types import Message, ReactionTypeEmoji

from bot import config
from bot.services.sale import SaleService
from bot.repositories import StatsRepository, ClientRepository
from bot.utils.parser import extract_payment_amounts, parse_client_data
from bot.db import get_pool

logger = logging.getLogger(__name__)
router = Router()

# Шаблоны для строк Trade In (игнорировать)
TRADE_IN_PATTERNS = [
    r'trade\s*in',
    r'трейд\s*ин',
    r'trade\-in',
    r'trade–in',
    r'trade—in',
    r'trade‑in',
]

def remove_trade_in_lines(text: str) -> str:
    """Удаляет строки, содержащие Trade In или его варианты."""
    lines = text.splitlines()
    filtered = []
    for line in lines:
        if any(re.search(p, line, re.IGNORECASE) for p in TRADE_IN_PATTERNS):
            logger.info(f"🔧 Игнорируем строку с Trade In: {line[:50]}")
            continue
        filtered.append(line)
    return '\n'.join(filtered)

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

    if await is_message_processed(message.chat.id, message.message_id):
        logger.info(f"Сообщение {message.message_id} уже обработано, пропускаем.")
        return

    # Удаляем строки с Trade In
    content = remove_trade_in_lines(content)

    # 1. Извлекаем суммы оплаты (игнорируем П/О)
    payments = extract_payment_amounts(content, ignore_prepay=True)

    # 2. Удаляем проданные товары (через SaleService)
    result = await SaleService.process_sale(content, message.chat.id, message.message_id)

    # 3. Сохраняем клиента (всегда, если есть данные)
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

    # 4. Сохраняем статистику продаж только если были удалены товары с серийными номерами
    count = len(result["sold_items"])
    logger.info(f"🔍 Продажа: найдено товаров с серийниками: {count}, sold_items={result['sold_items']}")

    if count > 0:
        await StatsRepository.add_sale(
            count=count,
            cash=payments['cash'],
            terminal=payments['terminal'],
            qr=payments['qr'],
            transfer=payments['transfer'],
            invoice=payments['invoice'],
            installment=payments['installment'],
            is_accessory=False
        )
        logger.info(f"✅ Продажа добавлена в статистику: товаров {count}, суммы: cash={payments['cash']}, term={payments['terminal']}, qr={payments['qr']}")
    else:
        logger.info("❌ Нет товаров с серийными номерами, статистика продаж НЕ сохранена (аксессуар или неверные серийники)")

    # 5. Сохраняем платежи в daily_payments (всегда, даже если аксессуар)
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            for pay_type, amount in payments.items():
                if amount > 0:
                    await conn.execute(
                        'INSERT INTO daily_payments (type, payment_type, amount) VALUES ($1, $2, $3)',
                        'sale', pay_type, amount
                    )
                    logger.info(f"💸 Платёж сохранён: sale {pay_type} = {amount}")

    # 6. Реакция и уведомления
    if result["sold_items"]:
        await message.react([ReactionTypeEmoji(emoji='🔥')])
    else:
        logger.info("Нет проданных товаров, реакция не ставится")

    if result["not_found"]:
        text = "❌ Серийные номера не найдены в ассортименте:\n" + "\n".join(result["not_found"])
        await message.reply(text)

    await mark_message_processed(message.chat.id, message.message_id)

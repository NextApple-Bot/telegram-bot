import logging
from aiogram import F, Router
from aiogram.types import Message, ReactionTypeEmoji

from bot import config
from bot.services.sale import SaleService
from bot.repositories import StatsRepository, ClientRepository
from bot.repositories.transaction import TransactionRepository
from bot.utils.parser import extract_payment_amounts, parse_client_data
from bot.db import get_pool

logger = logging.getLogger(__name__)
router = Router()

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

    # 1. Извлекаем суммы оплаты (игнорируем П/О)
    payments = extract_payment_amounts(content, ignore_prepay=True)

    # 2. Удаляем проданные товары (через SaleService)
    result = await SaleService.process_sale(content, message.chat.id, message.message_id)

    # 3. Сохраняем клиента
    client_id = None
    try:
        data = parse_client_data(content)
        if data['phones'] or data['full_name']:
            client_id = await ClientRepository.get_or_create_client(
                phone=data['main_phone'],
                phones=data['phones'],
                full_name=data['full_name'],
                telegram_username=data['telegram_username'],
                social_network=data['social_network'],
                referral_source=data['referral_source']
            )
    except Exception as e:
        logger.exception(f"Ошибка при сохранении клиента: {e}")

    # 4. Создаём транзакции (финансы)
    for pay_type, amount in payments.items():
        if amount > 0:
            await TransactionRepository.add_transaction(
                t_type='sale',
                payment_type=pay_type,
                amount=amount,
                message_id=message.message_id,
                client_id=client_id
            )
            logger.info(f"Создана транзакция: {pay_type} = {amount}")

    # 5. Сохраняем статистику продаж (количество продаж)
    count = len(result["sold_items"])
    is_accessory = (count == 0)
    await StatsRepository.add_sale(
        count=count,
        cash=payments['cash'],
        terminal=payments['terminal'],
        qr=payments['qr'],
        transfer=payments['transfer'],
        invoice=payments['invoice'],
        installment=payments['installment'],
        is_accessory=is_accessory
    )

    # 6. Реакция и уведомления
    if result["sold_items"]:
        await message.react([ReactionTypeEmoji(emoji='🔥')])
    else:
        logger.info("Нет проданных товаров, реакция не ставится")

    if result["not_found"]:
        text = "❌ Серийные номера не найдены в ассортименте:\n" + "\n".join(result["not_found"])
        await message.reply(text)

    await mark_message_processed(message.chat.id, message.message_id)

import logging
from aiogram import F, Router
from aiogram.types import Message, ReactionTypeEmoji

import config
import inventory
import stats
from utils import extract_payment_amounts
from serial_utils import extract_serials_from_text
from database import get_item_id_by_serial
from inventory import remove_by_serial
from client_parser import parse_client_data
from database import get_or_create_client, add_purchase

logger = logging.getLogger(__name__)
router = Router()

@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_SALES,
    (F.text | F.caption)
)
async def handle_sales_message(message: Message):
    """Обрабатывает сообщение в топике Продажи (текст или подпись к медиа)."""
    content = message.text or message.caption
    if not content:
        return

    # 1. Извлекаем суммы оплат (игнорируем П/О)
    payments = extract_payment_amounts(content, ignore_prepay=True)
    cash = payments['cash']
    terminal = payments['terminal']
    qr = payments['qr']
    transfer = payments['transfer']
    invoice = payments['invoice']
    installment = payments['installment']

    # 2. Извлекаем все уникальные серийные номера
    serials = list(set(extract_serials_from_text(content)))
    logger.info(f"🔍 Найденные серийники: {serials}")

    sold_items = []  # список кортежей (item_id, serial)

    # 3. Проверяем каждый серийный номер в БД
    for serial in serials:
        item_id = await get_item_id_by_serial(serial)
        if item_id:
            sold_items.append((item_id, serial))
            logger.info(f"✅ Серийник {serial} найден в БД")
        else:
            logger.warning(f"❌ Серийник {serial} не найден в БД")

    # 4. Удаляем найденные товары (с причиной 'sale')
    if sold_items:
        for item_id, serial in sold_items:
            removed = await remove_by_serial(serial, reason='sale')
            if removed:
                logger.info(f"🗑️ Товар {serial} удалён")
            else:
                logger.warning(f"⚠️ Не удалось удалить товар {serial}")

    # 5. Сохраняем запись о продаже
    count = len(sold_items)
    is_accessory = (count == 0)

    await stats.increment_sales(
        count=count,
        cash=cash,
        terminal=terminal,
        qr=qr,
        transfer=transfer,
        invoice=invoice,
        installment=installment,
        item_id=None,
        is_accessory=is_accessory
    )
    logger.info(f"Продажа: товаров {count}, суммы: cash={cash}, term={terminal}, qr={qr}, transfer={transfer}, invoice={invoice}, inst={installment}")

    # 6. Формируем список серийников, которые не были найдены
    not_found = [s for s in serials if s not in [x[1] for x in sold_items]]
    if not_found:
        text = "❌ Серийные номера не найдены в ассортименте:\n" + "\n".join(not_found)
        await message.reply(text)

    # 7. Ставим реакцию, если были какие-то операции
    if sold_items or any(payments.values()):
        try:
            await message.react([ReactionTypeEmoji(emoji='🔥')])
        except Exception as e:
            logger.exception(f"Не удалось поставить реакцию: {e}")

    # 8. Сохранение данных клиента и покупки
    try:
        data = parse_client_data(content)
        if data['phones'] or data['full_name']:
            client_id = await get_or_create_client(
                phone=data['main_phone'],
                phones=data['phones'],
                full_name=data['full_name'],
                telegram_username=data['telegram_username'],
                social_network=data['social_network'],
                referral_source=data['referral_source']
            )
            await add_purchase(
                client_id=client_id,
                items=data['items'],
                total_amount=data['total'],
                payment_details=data['payments'],
                purchase_type='sale'
            )
            logger.info(f"Сохранены данные клиента {client_id}")
    except Exception as e:
        logger.exception(f"Ошибка при сохранении данных клиента: {e}")

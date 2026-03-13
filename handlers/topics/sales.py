import logging
from aiogram import F, Router
from aiogram.types import Message, ReactionTypeEmoji

import config
import inventory
import stats
from utils import extract_sales_amounts
from serial_utils import extract_serials_from_text
from database import get_item_id_by_serial, remove_item_by_serial

# Импорты для клиентов
from client_parser import parse_client_data
from database import get_or_create_client, add_purchase

logger = logging.getLogger(__name__)
router = Router()

@router.message(F.chat.id == config.MAIN_GROUP_ID, F.message_thread_id == config.THREAD_SALES)
async def handle_sales_message(message: Message):
    """Обрабатывает сообщение в топике Продажи."""
    if not message.text:
        return

    lines = message.text.splitlines()
    cash, terminal, qr, installment = extract_sales_amounts(lines)

    candidates = extract_serials_from_text(message.text)
    found_serials = []
    not_found_serials = []
    sold_items = []  # список кортежей (item_id, serial)

    for cand in candidates:
        item_id = await get_item_id_by_serial(cand)
        if item_id:
            found_serials.append(cand)
            sold_items.append((item_id, cand))
        else:
            not_found_serials.append(cand)

    if sold_items:
        per_item_cash = cash / len(sold_items) if cash else 0
        per_item_terminal = terminal / len(sold_items) if terminal else 0
        per_item_qr = qr / len(sold_items) if qr else 0
        per_item_installment = installment / len(sold_items) if installment else 0
        for item_id, serial in sold_items:
            await stats.increment_sales(
                count=1,
                cash=per_item_cash,
                terminal=per_item_terminal,
                qr=per_item_qr,
                installment=per_item_installment,
                item_id=item_id,
                is_accessory=False
            )
            logger.info(f"✅ Продажа зарегистрирована для товара {serial} (item_id={item_id})")

        for item_id, serial in sold_items:
            removed = await remove_item_by_serial(serial)
            if not removed:
                logger.warning(f"⚠️ Не удалось удалить товар {serial} после регистрации продажи")
            else:
                logger.info(f"🗑️ Товар {serial} удалён из ассортимента")

    elif cash or terminal or qr or installment:
        await stats.increment_sales(
            count=1,
            cash=cash,
            terminal=terminal,
            qr=qr,
            installment=installment,
            item_id=None,
            is_accessory=True
        )
        logger.info(f"✅ Зарегистрирована продажа аксессуаров на сумму {cash+terminal+qr+installment:.0f} руб.")

    if not_found_serials:
        text = "❌ Серийные номера не найдены в ассортименте:\n" + "\n".join(not_found_serials)
        await message.reply(text)
        logger.info(f"❌ Не найдены: {not_found_serials}")

    if sold_items:
        try:
            await message.react([ReactionTypeEmoji(emoji='🔥')])
        except Exception as e:
            logger.exception(f"Не удалось поставить реакцию: {e}")

    # Сохранение данных клиента
    try:
        data = parse_client_data(message.text)
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
            logger.info(f"✅ Сохранены данные клиента {client_id} с покупкой, телефоны: {data['phones']}")
    except ImportError as e:
        logger.error(f"❌ Ошибка импорта в client_parser: {e}")
    except Exception as e:
        logger.exception(f"❌ Неожиданная ошибка при сохранении данных клиента: {e}")

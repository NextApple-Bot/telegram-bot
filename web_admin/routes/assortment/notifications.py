# Файл: web_admin/routes/assortment/notifications.py
import logging
from aiogram import Bot
from bot import config

logger = logging.getLogger(__name__)


def format_number(value: float) -> str:
    if value is None:
        return ""
    return f"{value:,.0f}".replace(",", " ")


async def send_booking_notification(
    item_text: str,
    serial: str,
    price: float = None,
    prepayment: float = None,
    platform: str = None,
    full_name: str = None,
    phone: str = None,
    payment_type: str = None,
    is_cancel: bool = False
):
    try:
        bot = Bot(token=config.TOKEN)
        if is_cancel:
            message_text = f"❌ Отмена Брони:\n\n{item_text}"
        else:
            remainder = 0
            if price and prepayment:
                remainder = price - prepayment

            prepayment_str = ""
            if prepayment is not None:
                prepayment_str = f"П/О – {format_number(prepayment)}"
                if payment_type:
                    payment_type_ru = {
                        'cash': 'Наличными', 'terminal': 'Терминал', 'qr': 'QR-код',
                        'transfer': 'Перевод', 'invoice': 'Оплата по счету', 'installment': 'Рассрочка'
                    }.get(payment_type, payment_type)
                    prepayment_str += f" ({payment_type_ru})"

            lines = ["БРОНЬ:\n", item_text]
            if price is not None:
                lines.append(f"Стоимость – {format_number(price)}")
                lines.append("")
                lines.append("")
            if prepayment_str:
                lines.append(prepayment_str)
                lines.append("")
            if price is not None and prepayment is not None:
                lines.append(f"Остаток – {format_number(remainder)}")
                lines.append("")
                lines.append(f"Общая – {format_number(price)}")
                lines.append("")
                lines.append("")
            if full_name:
                lines.append(full_name)
            if phone:
                lines.append(phone)
            lines.append("")
            if platform:
                lines.append(f"Площадка – {platform}")

            message_text = "\n".join(lines)

        await bot.send_message(
            chat_id=config.MAIN_GROUP_ID,
            text=message_text,
            message_thread_id=config.THREAD_PREORDER
        )
        await bot.session.close()
        logger.info(f"✅ Уведомление о брони отправлено: {item_text}")
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке уведомления о брони: {e}")


async def send_sale_notification(
    item_text: str,
    price: float,
    payment_type: str,
    prepayment: float = None,
    payment_amount: float = None,
    platform: str = None,
    full_name: str = None,
    phone: str = None,
    accessories: list = None
):
    try:
        bot = Bot(token=config.TOKEN)
        payment_type_ru = {
            'cash': 'Наличными', 'terminal': 'Терминал', 'qr': 'QR-код',
            'transfer': 'Перевод', 'invoice': 'Оплата по счету', 'installment': 'Рассрочка'
        }

        lines = [item_text]
        lines.append(f"Стоимость – {format_number(price)}")
        lines.append("")   # одна пустая строка перед аксессуарами или оплатой

        # Дополнительные товары
        if accessories:
            for acc in accessories:
                lines.append(acc['text'])
                lines.append(f"Стоимость – {format_number(acc['price'])}")
                lines.append("")   # одна пустая строка после каждого аксессуара
            lines.append("")       # дополнительная пустая строка, чтобы получить две перед оплатой
        else:
            lines.append("")       # вторая пустая строка перед оплатой

        # Сбор сумм по способам оплаты
        payments = {}
        if payment_amount and payment_amount > 0 and payment_type:
            payments[payment_type] = payments.get(payment_type, 0) + payment_amount

        if accessories:
            for acc in accessories:
                if acc.get('payment_type') and acc['price'] > 0:
                    payments[acc['payment_type']] = payments.get(acc['payment_type'], 0) + acc['price']

        # Строки оплаты
        for pt, amount in payments.items():
            if amount > 0:
                lines.append(f"{payment_type_ru.get(pt, pt)} – {format_number(amount)}")
                lines.append("")   # одна пустая строка после каждого способа оплаты

        # Удаляем последнюю пустую строку (если она есть) и добавляем одну перед "Общая"
        if lines and lines[-1] == "":
            lines.pop()
        lines.append("")   # одна пустая строка перед "Общая"

        total_paid = (prepayment or 0) + sum(payments.values())
        lines.append(f"Общая – {format_number(total_paid)}")
        lines.append("")
        lines.append("")   # две пустые строки перед ФИО

        if full_name:
            lines.append(full_name)
        if phone:
            lines.append(phone)
        lines.append("")
        if platform:
            lines.append(f"Площадка – {platform}")

        message_text = "\n".join(lines)
        await bot.send_message(
            chat_id=config.MAIN_GROUP_ID,
            text=message_text,
            message_thread_id=config.THREAD_SALES
        )
        await bot.session.close()
        logger.info(f"✅ Уведомление о продаже отправлено: {item_text}")
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке уведомления о продаже: {e}")

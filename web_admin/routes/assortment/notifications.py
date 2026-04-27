# Файл: web_admin/routes/assortment/notifications.py
import logging
import asyncio
from datetime import datetime
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

            # Дата брони теперь в формате ДД.ММ.ГГ
            today = datetime.now().strftime("%d.%m.%y")
            lines = ["БРОНЬ:\n", f"{item_text} (Бронь от {today})"]
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
            'transfer': 'Перевод', 'invoice': 'Оплата по счету', 'installment': 'Рассрочка',
            'paid': 'Оплачен'
        }

        lines = [item_text]
        lines.append(f"Стоимость – {format_number(price)}")
        lines.append("")

        if accessories:
            for acc in accessories:
                lines.append(acc['text'])
                lines.append(f"Стоимость – {format_number(acc['price'])}")
                lines.append("")
            lines.append("")
        else:
            lines.append("")

        # Собираем платежи (кроме paid) для расчёта общей суммы
        payments = {}
        if payment_type != "paid" and payment_amount and payment_amount > 0:
            payments[payment_type] = payments.get(payment_type, 0) + payment_amount

        if accessories:
            for acc in accessories:
                pay_type = acc.get('payment_type')
                if pay_type and pay_type != "paid" and acc['price'] > 0:
                    payments[pay_type] = payments.get(pay_type, 0) + acc['price']

        # Строки оплаты
        if payment_type == "paid":
            lines.append("Оплачен")
            lines.append("")
        else:
            for pt, amount in payments.items():
                if amount > 0:
                    lines.append(f"{payment_type_ru.get(pt, pt)} – {format_number(amount)}")
                    lines.append("")

        if lines and lines[-1] == "":
            lines.pop()
        lines.append("")

        total_paid = (prepayment or 0) + sum(payments.values())
        lines.append(f"Общая – {format_number(total_paid)}")
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
            message_thread_id=config.THREAD_SALES
        )
        await bot.session.close()
        logger.info(f"✅ Уведомление о продаже отправлено: {item_text}")
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке уведомления о продаже: {e}")

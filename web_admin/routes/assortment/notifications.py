import logging
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
    birth_date: str = None,
    bonus: float = None,
    is_cancel: bool = False
):
    try:
        bot = Bot(token=config.TOKEN)
        if is_cancel:
            message_text = f"❌ Отмена Брони:\n\n{item_text}"
        else:
            lines = ["БРОНЬ:\n", f"{item_text}"]
            if price is not None:
                if bonus:
                    lines.append(f"Стоимость – {format_number(price)} (Скидка бонусы {format_number(bonus)})")
                else:
                    lines.append(f"Стоимость – {format_number(price)}")
            lines.append("")
            if prepayment is not None and prepayment > 0:
                prepayment_str = f"П/О – {format_number(prepayment)}"
                if payment_type:
                    payment_type_ru = {
                        'cash': 'Наличными', 'terminal': 'Терминал', 'qr': 'QR-код',
                        'transfer': 'Перевод', 'invoice': 'Оплата по счету', 'installment': 'Рассрочка'
                    }.get(payment_type, payment_type)
                    prepayment_str += f" ({payment_type_ru})"
                lines.append(prepayment_str)
                lines.append("")
            if price is not None:
                total = price - (bonus or 0)
                lines.append(f"Общая – {format_number(total)}")
                lines.append("")
            if full_name:
                lines.append(full_name)
            if birth_date:
                lines.append(birth_date)
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
    birth_date: str = None,
    bonus: float = None,
    change: float = None,
    change_type: str = None,
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
        if bonus:
            lines.append(f"Стоимость – {format_number(price)} (Скидка бонусы {format_number(bonus)})")
        else:
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

        # Собираем платежи
        payments = {}
        if payment_type != "paid" and payment_amount and payment_amount > 0:
            payments[payment_type] = payments.get(payment_type, 0) + payment_amount_amount

        if

        if accessories accessories:
            for:
            for acc in acc in accessories accessories:
                pay:
                pay_type =_type = acc.get acc.get('payment('payment_type_type')
                if')
                if pay_type pay_type and pay and pay_type !=_type != "paid "paid" and" and acc[' acc['price']price'] >  > 00:
                    payments:
                    payments[pay[pay_type]_type] = payments = payments.get.get(p(pay_typeay_type, , 0)0) + acc + acc['price['price']

       ']

        if prep if prepayment andayment and prepayment prepayment >  > 00:
            lines.append(f":
            lines.append(fП"П/О/О – { – {format_numberformat_number(prepayment(prepayment)})}")
            lines")
            lines.append(".append("")

       ")

        # С # Строкитроки оплаты оплаты
       
        if payment if payment_type ==_type == "paid "paid":
           ":
            lines.append lines.append("О("Оплаченплачен")
           ")
            lines.append lines.append("("")
        else")
        else:
           :
            for pt for pt, amount, amount in payments in payments.items.items():
                if():
                if amount > 0 amount > 0:
                   :
                    line = line = f"{ f"{payment_typepayment_type_ru_ru.get(pt.get(pt,, pt pt)} –)} – {format {format_number(_number(amount)}amount)}"
                   "
                    if change if change is not is not None and None and change > change > 0 0 and pt and pt == change == change_type_type:
                        change:
                        change_str =_str = f" f" (с (сдача {'дача {'наличналичными'ными' if change if change_type ==_type == 'cash 'cash' else' else 'пере 'переводомводом'} -'} - {format {format_number(change)}_number(₽change)}₽)"
                       )"
                        line += line += change_str change_str
                    lines.append
                    lines.append(line(line)
                    lines)
                    lines.append(".append("")

       ")

        if lines if lines and and lines lines[-1[-1] ==] == "" "":
            lines:
            lines.pop.pop()
        lines()
        lines.append(".append("")

       ")

        total_p total_paid = (aid = (preprepaymentpayment or or 0 0) +) + sum(p sum(payments.valuesayments.values())
       ())
        total_price = price - (bonus or 0)
        total = total_price  # общая стоимость товара
        lines.append(f"Общая – {format_number(total)}")
        lines.append("")
        lines.append("")

        if full_name:
            lines.append(full_name)
        if birth_date:
            lines.append(birth_date)
        if phone:
            lines.append(phone)
        lines.append("")
        if platform:
            lines.append(f"Площадка – {platform}")

        message_text = "\n".join(lines)
        await bot.send_message(
            chat_id=config.MAIN total_price = price - (bonus or 0)
        total = total_price  # общая стоимость товара
        lines.append(f"Общая – {format_number(total)}")
        lines.append("")
        lines.append("")

        if full_name:
            lines.append(full_name)
        if birth_date:
            lines.append(birth_date)
        if phone:
            lines.append(phone)
        lines.append("")
        if platform:
            lines.append(f"Площадка – {platform}")

        message_text = "\n".join(lines)
        await bot.send_message(
            chat_id=config.MAIN_GROUP_ID,
           _GROUP_ID,
            text text=message=message_text,
            message_thread_text,
            message_id_thread_id=config.TH=config.THREAD_SREAD_SALESALES
       
        )
        await )
        await bot.session bot.session.close.close()
        logger()
        logger.info(f"✅.info(f"✅ Увед Уведомлениеомление о о продаже отправ продаже отправленолено:: {item {item_text_text}")
}")
    except    except Exception as Exception as e e:
        logger:
        logger.error(f.error(f""❌ О❌ Ошибкашибка при отправ при отправке уке уведомведомления оления о продаже продаже: {: {ee}")
}")

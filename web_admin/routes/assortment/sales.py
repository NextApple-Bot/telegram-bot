# Файл: web_admin/routes/assortment/sales.py
import time
import logging
from bot.repositories import StatsRepository
from bot.db import get_pool

logger = logging.getLogger(__name__)


def generate_sale_message_id() -> int:
    """Генерирует уникальный ID сообщения о продаже (на основе времени)."""
    return int(time.time() * 1000)


async def delete_item_and_log_sale(
    item_id: int,
    text: str,
    serial: str,
    category_id: int,
    price: float,                # общая стоимость всех товаров в продаже
    prepayment: float,
    payment_type: str,           # НЕ ИСПОЛЬЗУЕТСЯ для daily_payments (оставлен для совместимости)
    payment_amount: float,       # НЕ ИСПОЛЬЗУЕТСЯ для daily_payments
    message_id: int
):
    """
    Удаляет основной товар из ассортимента и создаёт запись в sales.
    Платежи в daily_payments теперь обрабатываются отдельно в handle_sale_from_form.
    """
    allowed_types = {'cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment'}
    if payment_type not in allowed_types:
        payment_type = 'cash'
        logger.warning(f"Некорректный payment_type, заменён на 'cash': {payment_type}")

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Архивируем удаляемый товар
            await conn.execute("""
                INSERT INTO deleted_items (item_id, text, serial, category_id, reason, sale_message_id)
                VALUES ($1, $2, $3, $4, 'sale_from_admin', $5)
            """, item_id, text, serial, category_id, message_id)
            # Удаляем товар из активного ассортимента
            await conn.execute("DELETE FROM items WHERE id = $1", item_id)

            # Записываем факт продажи в статистику (общая стоимость всех товаров)
            await StatsRepository.add_sale(
                count=1,
                cash=0,          # платежи будут учтены отдельно в daily_payments
                terminal=0,
                qr=0,
                transfer=0,
                invoice=0,
                installment=0,
                is_accessory=False,
                message_id=message_id,
                conn=conn
            )
            # ВАЖНО: больше НЕ вставляем запись в daily_payments здесь.
            # Это будет сделано в handle_sale_from_form с учётом аксессуаров.


async def handle_sale_from_form(
    item_id: int,
    text: str,
    serial: str,
    category_id: int,
    old_text: str,
    old_serial: str,
    old_category_id: int,
    sale_price: float,
    sale_prepayment: float,
    sale_payment_amount: float,
    sale_payment_type: str,
    sale_platform: str,
    sale_full_name: str,
    sale_phone: str,
    accessories: list = None
):
    """
    Основная логика продажи из веб-админки.
    """
    if not sale_price:
        raise ValueError("Укажите стоимость продажи")
    if not sale_payment_amount or sale_payment_amount <= 0:
        raise ValueError("Укажите сумму оплаты")
    if not sale_payment_type:
        sale_payment_type = "cash"

    sale_message_id = generate_sale_message_id()

    # ----------------------------------------------------------------------
    # 1. Обработка дополнительных товаров (аксессуаров)
    # ----------------------------------------------------------------------
    accessories_total = 0
    processed_accessories = []   # для уведомления
    accessories_payments = {}    # {payment_type: сумма}

    if accessories:
        pool = await get_pool()
        async with pool.acquire() as conn:
            for acc in accessories:
                acc_price = acc['price']
                accessories_total += acc_price

                display_text = acc['name']
                item_info = None

                # Если указан серийный номер, ищем товар в БД
                if acc.get('serial'):
                    row = await conn.fetchrow("""
                        SELECT id, text, category_id FROM items
                        WHERE UPPER(serial) = $1
                    """, acc['serial'].strip().upper())
                    if row:
                        item_info = dict(row)
                        display_text = item_info['text']
                        # Удаляем товар из ассортимента
                        await conn.execute("""
                            INSERT INTO deleted_items (item_id, text, serial, category_id, reason, sale_message_id)
                            VALUES ($1, $2, $3, $4, 'sale_from_admin', $5)
                        """, item_info['id'], item_info['text'], acc['serial'], item_info['category_id'], sale_message_id)
                        await conn.execute("DELETE FROM items WHERE id = $1", item_info['id'])
                        # Фиксируем продажу дополнительного товара (без учёта платежа здесь)
                        await StatsRepository.add_sale(
                            count=1,
                            cash=0, terminal=0, qr=0, transfer=0, invoice=0, installment=0,
                            is_accessory=False,
                            message_id=sale_message_id,
                            conn=conn
                        )

                # Сохраняем для уведомления
                processed_accessories.append({
                    "text": display_text,
                    "price": acc_price,
                    "payment_type": acc.get('payment_type')
                })

                # Суммируем платежи аксессуаров по типам
                pay_type = acc.get('payment_type')
                if pay_type and acc_price > 0:
                    accessories_payments[pay_type] = accessories_payments.get(pay_type, 0) + acc_price

    # ----------------------------------------------------------------------
    # 2. Суммируем все платежи (основной + аксессуары)
    # ----------------------------------------------------------------------
    all_payments = dict(accessories_payments)  # копируем
    if sale_payment_amount > 0 and sale_payment_type:
        all_payments[sale_payment_type] = all_payments.get(sale_payment_type, 0) + sale_payment_amount

    # ----------------------------------------------------------------------
    # 3. Сохраняем платежи в daily_payments
    # ----------------------------------------------------------------------
    pool = await get_pool()
    async with pool.acquire() as conn:
        for pay_type, amount in all_payments.items():
            if amount > 0:
                await conn.execute("""
                    INSERT INTO daily_payments (type, payment_type, amount, sale_message_id)
                    VALUES ('sale', $1, $2, $3)
                """, pay_type, amount, sale_message_id)

    # ----------------------------------------------------------------------
    # 4. Общая стоимость всех товаров
    # ----------------------------------------------------------------------
    total_item_price = sale_price + accessories_total

    logger.info(
        f"Продажа товара {item_id}: цена={total_item_price}, "
        f"платежи={all_payments}, аксессуары={accessories_total}"
    )

    # ----------------------------------------------------------------------
    # 5. Отправляем уведомление в Telegram
    # ----------------------------------------------------------------------
    from .notifications import send_sale_notification
    await send_sale_notification(
        item_text=text,
        price=sale_price,
        payment_type=sale_payment_type,
        prepayment=sale_prepayment if sale_prepayment and sale_prepayment > 0 else None,
        payment_amount=sale_payment_amount,
        platform=sale_platform,
        full_name=sale_full_name,
        phone=sale_phone,
        accessories=processed_accessories
    )

    # ----------------------------------------------------------------------
    # 6. Удаляем основной товар и пишем статистику продажи
    # ----------------------------------------------------------------------
    await delete_item_and_log_sale(
        item_id=item_id,
        text=old_text,
        serial=old_serial,
        category_id=old_category_id,
        price=total_item_price,
        prepayment=sale_prepayment or 0,
        payment_type=sale_payment_type,
        payment_amount=sale_payment_amount,
        message_id=sale_message_id
    )

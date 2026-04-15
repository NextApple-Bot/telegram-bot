# Файл: web_admin/routes/assortment/sales.py
import uuid
import logging
from bot.repositories import StatsRepository
from bot.db import get_pool

logger = logging.getLogger(__name__)


def generate_sale_message_id() -> int:
    """Генерирует уникальный положительный ID для продажи."""
    # Используем 63 бита UUID4, чтобы избежать коллизий и отрицательных чисел
    return uuid.uuid4().int & 0x7FFFFFFFFFFFFFFF


async def delete_item_and_log_sale(
    item_id: int,
    text: str,
    serial: str,
    category_id: int,
    price: float,
    prepayment: float,
    payment_type: str,
    payment_amount: float,
    message_id: int
):
    allowed_types = {'cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment'}
    if payment_type not in allowed_types:
        payment_type = 'cash'
        logger.warning(f"Некорректный payment_type, заменён на 'cash': {payment_type}")

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("""
                INSERT INTO deleted_items (item_id, text, serial, category_id, reason, sale_message_id)
                VALUES ($1, $2, $3, $4, 'sale_from_admin', $5)
            """, item_id, text, serial, category_id, message_id)
            await conn.execute("DELETE FROM items WHERE id = $1", item_id)
            await StatsRepository.add_sale(
                count=1,
                cash=payment_type == 'cash' and payment_amount or 0,
                terminal=payment_type == 'terminal' and payment_amount or 0,
                qr=payment_type == 'qr' and payment_amount or 0,
                transfer=payment_type == 'transfer' and payment_amount or 0,
                invoice=payment_type == 'invoice' and payment_amount or 0,
                installment=payment_type == 'installment' and payment_amount or 0,
                is_accessory=False,
                message_id=message_id,
                conn=conn
            )
            await conn.execute("""
                INSERT INTO daily_payments (type, payment_type, amount, sale_message_id)
                VALUES ('sale', $1, $2, $3)
            """, payment_type, payment_amount, message_id)


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
    if not sale_price:
        raise ValueError("Укажите стоимость продажи")
    if not sale_payment_amount or sale_payment_amount <= 0:
        raise ValueError("Укажите сумму оплаты")
    if not sale_payment_type:
        sale_payment_type = "cash"

    sale_message_id = generate_sale_message_id()

    accessories_total = 0
    processed_accessories = []
    accessories_payments = {}

    if accessories:
        pool = await get_pool()
        async with pool.acquire() as conn:
            for acc in accessories:
                acc_price = acc['price']
                accessories_total += acc_price

                display_text = acc['name']
                item_info = None

                if acc.get('serial'):
                    row = await conn.fetchrow("""
                        SELECT id, text, category_id FROM items
                        WHERE UPPER(serial) = $1
                    """, acc['serial'].strip().upper())
                    if row:
                        item_info = dict(row)
                        display_text = item_info['text']
                        await conn.execute("""
                            INSERT INTO deleted_items (item_id, text, serial, category_id, reason, sale_message_id)
                            VALUES ($1, $2, $3, $4, 'sale_from_admin', $5)
                        """, item_info['id'], item_info['text'], acc['serial'], item_info['category_id'], sale_message_id)
                        await conn.execute("DELETE FROM items WHERE id = $1", item_info['id'])
                        await StatsRepository.add_sale(
                            count=1,
                            cash=0, terminal=0, qr=0, transfer=0, invoice=0, installment=0,
                            is_accessory=False,
                            message_id=sale_message_id,
                            conn=conn
                        )

                processed_accessories.append({
                    "text": display_text,
                    "price": acc_price,
                    "payment_type": acc.get('payment_type')
                })

                pay_type = acc.get('payment_type')
                if pay_type and acc_price > 0:
                    accessories_payments[pay_type] = accessories_payments.get(pay_type, 0) + acc_price

    all_payments = dict(accessories_payments)
    if sale_payment_amount > 0 and sale_payment_type:
        all_payments[sale_payment_type] = all_payments.get(sale_payment_type, 0) + sale_payment_amount

    pool = await get_pool()
    async with pool.acquire() as conn:
        for pay_type, amount in all_payments.items():
            if amount > 0:
                await conn.execute("""
                    INSERT INTO daily_payments (type, payment_type, amount, sale_message_id)
                    VALUES ('sale', $1, $2, $3)
                """, pay_type, amount, sale_message_id)

    total_item_price = sale_price + accessories_total

    logger.info(
        f"Продажа товара {item_id}: цена={total_item_price}, "
        f"платежи={all_payments}, аксессуары={accessories_total}"
    )

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

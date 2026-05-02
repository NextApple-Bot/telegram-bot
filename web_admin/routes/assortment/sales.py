# Файл: web_admin/routes/assortment/sales.py
import asyncio
import logging
import uuid
from datetime import date

from bot.db import get_pool
from bot.repositories import ClientRepository, StatsRepository
from bot.services.cache import cache

logger = logging.getLogger(__name__)


def generate_sale_message_id() -> int:
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
    message_id: int,
    conn
):
    allowed_types = {'cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment', 'paid'}
    if payment_type not in allowed_types:
        payment_type = 'cash'
        logger.warning(f"Некорректный payment_type, заменён на 'cash': {payment_type}")

    try:
        await conn.execute("""
            INSERT INTO deleted_items (item_id, text, serial, category_id, reason, sale_message_id)
            VALUES ($1, $2, $3, $4, 'sale_from_admin', $5)
        """, item_id, text, serial, category_id, message_id)
    except Exception as e:
        logger.warning(f"Не удалось вставить в deleted_items для item_id={item_id}: {e}")

    await conn.execute("DELETE FROM items WHERE id = $1", item_id)
    await StatsRepository.add_sale(
        count=1,
        cash=0,
        terminal=0,
        qr=0,
        transfer=0,
        invoice=0,
        installment=0,
        is_accessory=False,
        message_id=message_id,
        conn=conn
    )


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
    accessories: list = None,
    sale_birth_date: str | None = None,
    conn=None
):
    try:
        if not sale_price:
            raise ValueError("Укажите стоимость продажи")
        if sale_payment_type != "paid" and (not sale_payment_amount or sale_payment_amount <= 0):
            raise ValueError("Укажите сумму оплаты")
        if not sale_payment_type:
            sale_payment_type = "cash"

        sale_message_id = generate_sale_message_id()

        accessories_total = 0
        processed_accessories = []
        accessories_payments = {}

        own_conn = False
        if conn is None:
            pool = await get_pool()
            conn = await pool.acquire()
            own_conn = True

        try:
            # --- Сохраняем или обновляем клиента ---
            client_id = None
            phone = sale_phone.strip() if sale_phone else None
            if phone or sale_full_name:
                client_id = await ClientRepository.get_or_create_client(
                    phone=phone,
                    full_name=sale_full_name.strip() if sale_full_name else None,
                    social_network=sale_platform.strip() if sale_platform else None,
                    birth_date=sale_birth_date,
                    conn=conn
                )

            # Обработка аксессуаров
            if accessories:
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
                            try:
                                await conn.execute("""
                                    INSERT INTO deleted_items (item_id, text, serial, category_id, reason, sale_message_id)
                                    VALUES ($1, $2, $3, $4, 'sale_from_admin', $5)
                                """, item_info['id'], item_info['text'], acc['serial'], item_info['category_id'], sale_message_id)
                            except Exception as e:
                                logger.warning(f"Не удалось вставить аксессуар в deleted_items: {e}")
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

Example objects:

import asyncpg
from datetime import date
import config
from database import add_preorder as db_add_preorder, add_sale as db_add_sale, add_booking, get_today_stats, get_pool

async def increment_preorder(cash=0.0, terminal=0.0, qr=0.0, transfer=0.0, invoice=0.0, installment=0.0):
    """Добавляет запись о предзаказе."""
    await db_add_preorder(cash, terminal, qr, transfer, invoice, installment)

async def increment_booking(serial: str, amount: float):
    """Добавляет бронь по серийному номеру."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT id FROM items WHERE UPPER(serial) = $1', serial.upper())
        if row:
            await conn.execute('''
                INSERT INTO bookings (item_id, total_amount) VALUES ($1, $2)
            ''', row['id'], amount)

async def increment_sales(count=1, cash=0.0, terminal=0.0, qr=0.0, transfer=0.0, invoice=0.0, installment=0.0, item_id=None, is_accessory=False):
    """Добавляет запись о продаже."""
    await db_add_sale(item_id, count, cash, terminal, qr, transfer, invoice, installment, is_accessory=is_accessory)

async def get_stats():
    """Возвращает статистику за сегодня."""
    return await get_today_stats()

async def reset_stats():
    """Сбрасывает статистику за сегодня."""
    today = date.today()
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('DELETE FROM preorders WHERE DATE(created_at) = $1', today)
            await conn.execute('DELETE FROM bookings WHERE DATE(booked_at) = $1', today)
            await conn.execute('DELETE FROM sales WHERE DATE(sold_at) = $1', today)

async def reset_finances():
    """Алиас для reset_stats (для совместимости)."""
    await reset_stats()

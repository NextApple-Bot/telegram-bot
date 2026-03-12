import asyncpg
from datetime import date
import config

async def increment_preorder(cash=0.0, terminal=0.0, qr=0.0, installment=0.0):
    conn = await asyncpg.connect(config.DATABASE_URL)
    try:
        await conn.execute('''
            INSERT INTO preorders (cash, terminal, qr, installment)
            VALUES ($1, $2, $3, $4)
        ''', cash, terminal, qr, installment)
    finally:
        await conn.close()

async def increment_booking(serial: str, amount: float):
    conn = await asyncpg.connect(config.DATABASE_URL)
    try:
        row = await conn.fetchrow('SELECT id FROM items WHERE UPPER(serial) = $1', serial.upper())
        if row:
            await conn.execute('''
                INSERT INTO bookings (item_id, total_amount) VALUES ($1, $2)
            ''', row['id'], amount)
    finally:
        await conn.close()

async def increment_sales(count=1, cash=0.0, terminal=0.0, qr=0.0, installment=0.0, item_id=None, is_accessory=False):
    await add_sale(item_id, count, cash, terminal, qr, installment, is_accessory=is_accessory)

async def get_stats():
    return await get_today_stats()

async def reset_stats():
    today = date.today()
    conn = await asyncpg.connect(config.DATABASE_URL)
    try:
        async with conn.transaction():
            await conn.execute('DELETE FROM preorders WHERE DATE(created_at) = $1', today)
            await conn.execute('DELETE FROM bookings WHERE DATE(booked_at) = $1', today)
            await conn.execute('DELETE FROM sales WHERE DATE(sold_at) = $1', today)
    finally:
        await conn.close()

async def reset_finances():
    await reset_stats()

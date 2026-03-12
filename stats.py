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

async def increment_sales(count=1, cash=0.0, terminal=0.0, qr=0.0, installment=0.0, item_id=None):
    conn = await asyncpg.connect(config.DATABASE_URL)
    try:
        await conn.execute('''
            INSERT INTO sales (item_id, count, cash, terminal, qr, installment)
            VALUES ($1, $2, $3, $4, $5, $6)
        ''', item_id, count, cash, terminal, qr, installment)
    finally:
        await conn.close()

async def get_stats():
    today = date.today()
    conn = await asyncpg.connect(config.DATABASE_URL)
    try:
        pre = await conn.fetchrow('''
            SELECT COUNT(*), COALESCE(SUM(cash),0), COALESCE(SUM(terminal),0),
                   COALESCE(SUM(qr),0), COALESCE(SUM(installment),0)
            FROM preorders WHERE DATE(created_at) = $1
        ''', today)
        pre_count, pc, pt, pq, pi = pre

        book = await conn.fetchrow('''
            SELECT COUNT(*), COALESCE(SUM(total_amount),0)
            FROM bookings WHERE DATE(booked_at) = $1
        ''', today)
        book_count, book_total = book

        sale = await conn.fetchrow('''
            SELECT COUNT(*), COALESCE(SUM(cash),0), COALESCE(SUM(terminal),0),
                   COALESCE(SUM(qr),0), COALESCE(SUM(installment),0)
            FROM sales WHERE DATE(sold_at) = $1
        ''', today)
        sale_count, sc, st, sq, si = sale

        return {
            'date': today.strftime('%Y-%m-%d'),
            'preorders': pre_count,
            'bookings': book_count,
            'sales': sale_count,
            'preorders_cash': pc,
            'preorders_terminal': pt,
            'preorders_qr': pq,
            'preorders_installment': pi,
            'bookings_total': book_total,
            'sales_cash': sc,
            'sales_terminal': st,
            'sales_qr': sq,
            'sales_installment': si,
        }
    finally:
        await conn.close()

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

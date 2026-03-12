from datetime import datetime
import aiosqlite
from database import get_today_stats, add_preorder, add_booking, add_sale, get_item_id_by_serial, DB_PATH

async def increment_preorder(cash=0.0, terminal=0.0, qr=0.0, installment=0.0):
    await add_preorder(cash, terminal, qr, installment)

async def increment_booking(serial: str, amount: float):
    item_id = await get_item_id_by_serial(serial)
    if item_id:
        await add_booking(item_id, amount)

async def increment_sales(count=1, cash=0.0, terminal=0.0, qr=0.0, installment=0.0, item_id=None):
    # Добавлен параметр item_id
    await add_sale(item_id, count, cash, terminal, qr, installment)

async def get_stats():
    return await get_today_stats()

async def reset_stats():
    today = datetime.now().strftime('%Y-%m-%d')
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM preorders WHERE DATE(created_at) = ?', (today,))
        await db.execute('DELETE FROM bookings WHERE DATE(booked_at) = ?', (today,))
        await db.execute('DELETE FROM sales WHERE DATE(sold_at) = ?', (today,))
        await db.commit()

async def reset_finances():
    await reset_stats()

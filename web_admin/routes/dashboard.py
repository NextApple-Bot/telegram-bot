# В начале файла, после других импортов
from bot.services.cache import cache  # <-- ДОБАВИТЬ

# ... остальной код ...

@router.post("/update_stats")
async def update_stats(data: UpdateStatsRequest):
    target_date_str = data.target_date
    lock_key = f"dashboard:update_stats:{target_date_str}"
    
    # Пытаемся захватить блокировку на 30 секунд
    if not await cache.lock(lock_key, ttl=30):
        return JSONResponse({"success": False, "error": "Обновление статистики уже выполняется"}, status_code=409)
    
    try:
        try:
            target_date = parse_date_any_format(data.target_date)
        except ValueError as e:
            return JSONResponse({"success": False, "error": str(e)}, status_code=400)

        pool = await get_pool()
        try:
            total_payments = data.cash + data.terminal + data.qr + data.transfer + data.invoice + data.installment
            if total_payments > 0 and data.sales_count == 0:
                data.sales_count = 1

            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute("DELETE FROM daily_payments WHERE DATE(created_at) = $1", target_date)
                    await conn.execute("DELETE FROM sales WHERE DATE(sold_at) = $1", target_date)
                    await conn.execute("DELETE FROM preorders WHERE DATE(created_at) = $1", target_date)
                    await conn.execute("DELETE FROM bookings WHERE DATE(booked_at) = $1", target_date)

                    payment_types = ['cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment']
                    for pt in payment_types:
                        amount = getattr(data, pt)
                        if amount > 0:
                            await conn.execute("""
                                INSERT INTO daily_payments (type, payment_type, amount, created_at)
                                VALUES ('sale', $1, $2, $3)
                            """, pt, amount, target_date)

                    if data.sales_count > 0:
                        await conn.execute("""
                            INSERT INTO sales (count, cash, terminal, qr, transfer, invoice, installment, sold_at)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        """, data.sales_count, data.cash, data.terminal, data.qr,
                            data.transfer, data.invoice, data.installment, target_date)

                    for _ in range(data.preorders_count):
                        await conn.execute("""
                            INSERT INTO preorders (cash, terminal, qr, transfer, invoice, installment, created_at)
                            VALUES ($1, $2, $3, $4, $5, $6, $7)
                        """, 0, 0, 0, 0, 0, 0, target_date)

                    for _ in range(data.bookings_count):
                        await conn.execute("""
                            INSERT INTO bookings (item_id, total_amount, booked_at)
                            VALUES (0, 0, $1)
                        """, target_date)

            logger.info(f"Статистика за {target_date} обновлена: {data.dict()}")
            return JSONResponse({"success": True})
        except Exception as e:
            logger.exception("Ошибка при обновлении статистики")
            return JSONResponse({"success": False, "error": str(e)}, status_code=500)
    finally:
        await cache.unlock(lock_key)

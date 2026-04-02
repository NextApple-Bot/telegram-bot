# Файл: bot/repositories/stats.py
from datetime import date
from bot.db import get_pool, retry_on_db_error
from typing import Dict

class StatsRepository:
    """Репозиторий для работы со статистикой (продажи, предзаказы, брони)."""

    @staticmethod
    @retry_on_db_error()
    async def add_sale(
        item_id: int = None,
        count: int = 1,
        cash: float = 0,
        terminal: float = 0,
        qr: float = 0,
        transfer: float = 0,
        invoice: float = 0,
        installment: float = 0,
        is_accessory: bool = False,
        message_id: int = None,
        conn=None
    ):
        """Добавляет запись о продаже с уникальным message_id."""
        if conn is None:
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute('''
                    INSERT INTO sales (item_id, count, cash, terminal, qr, transfer, invoice, installment, is_accessory, message_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (message_id) DO NOTHING
                ''', item_id, count, cash, terminal, qr, transfer, invoice, installment, is_accessory, message_id)
        else:
            await conn.execute('''
                INSERT INTO sales (item_id, count, cash, terminal, qr, transfer, invoice, installment, is_accessory, message_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (message_id) DO NOTHING
            ''', item_id, count, cash, terminal, qr, transfer, invoice, installment, is_accessory, message_id)

    @staticmethod
    @retry_on_db_error()
    async def add_preorder(cash=0, terminal=0, qr=0, transfer=0, invoice=0, installment=0):
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO preorders (cash, terminal, qr, transfer, invoice, installment)
                VALUES ($1, $2, $3, $4, $5, $6)
            ''', cash, terminal, qr, transfer, invoice, installment)

    @staticmethod
    @retry_on_db_error()
    async def add_booking(item_id: int, total_amount: float):
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO bookings (item_id, total_amount) VALUES ($1, $2)
            ''', item_id, total_amount)

    @staticmethod
    @retry_on_db_error()
    async def get_today_stats() -> Dict:
        today = date.today()
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Продажи
            sale_sums = await conn.fetchrow('''
                SELECT 
                    COALESCE(SUM(cash),0) as cash,
                    COALESCE(SUM(terminal),0) as terminal,
                    COALESCE(SUM(qr),0) as qr,
                    COALESCE(SUM(transfer),0) as transfer,
                    COALESCE(SUM(invoice),0) as invoice,
                    COALESCE(SUM(installment),0) as installment,
                    COUNT(*) as sales_count
                FROM sales 
                WHERE DATE(sold_at) = $1
            ''', today)

            # Предзаказы
            pre_sums = await conn.fetchrow('''
                SELECT 
                    COALESCE(SUM(cash),0) as cash,
                    COALESCE(SUM(terminal),0) as terminal,
                    COALESCE(SUM(qr),0) as qr,
                    COALESCE(SUM(transfer),0) as transfer,
                    COALESCE(SUM(invoice),0) as invoice,
                    COALESCE(SUM(installment),0) as installment,
                    COUNT(*) as preorders_count
                FROM preorders 
                WHERE DATE(created_at) = $1
            ''', today)

            # Брони
            book_sums = await conn.fetchrow('''
                SELECT 
                    COALESCE(SUM(total_amount),0) as total,
                    COUNT(*) as bookings_count
                FROM bookings 
                WHERE DATE(booked_at) = $1
            ''', today)

            return {
                'date': today.strftime('%Y-%m-%d'),
                'preorders_count': pre_sums['preorders_count'],
                'bookings_count': book_sums['bookings_count'],
                'sales_count': sale_sums['sales_count'],
                'preorders': {
                    'cash': pre_sums['cash'],
                    'terminal': pre_sums['terminal'],
                    'qr': pre_sums['qr'],
                    'transfer': pre_sums['transfer'],
                    'invoice': pre_sums['invoice'],
                    'installment': pre_sums['installment'],
                },
                'sales': {
                    'cash': sale_sums['cash'],
                    'terminal': sale_sums['terminal'],
                    'qr': sale_sums['qr'],
                    'transfer': sale_sums['transfer'],
                    'invoice': sale_sums['invoice'],
                    'installment': sale_sums['installment'],
                },
                'bookings_total': book_sums['total'],
            }

    @staticmethod
    @retry_on_db_error()
    async def reset_today_stats():
        """Удаляет статистику продаж, предзаказов, броней и финансов за сегодня."""
        today = date.today()
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Удаляем статистику продаж, предзаказов, броней
                await conn.execute('DELETE FROM preorders WHERE DATE(created_at) = $1', today)
                await conn.execute('DELETE FROM bookings WHERE DATE(booked_at) = $1', today)
                await conn.execute('DELETE FROM sales WHERE DATE(sold_at) = $1', today)
                # Также удаляем финансовые записи за сегодня
                await conn.execute('DELETE FROM daily_payments WHERE DATE(created_at) = $1', today)

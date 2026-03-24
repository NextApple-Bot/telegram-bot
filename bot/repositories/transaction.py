import logging
from typing import List, Dict
from bot.db import get_pool, retry_on_db_error
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class TransactionRepository:
    @staticmethod
    @retry_on_db_error()
    async def add_transaction(
        t_type: str,
        payment_type: str,
        amount: float,
        message_id: int,
        client_id: int = None
    ) -> int:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow('''
                INSERT INTO transactions (type, payment_type, amount, message_id, client_id)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
            ''', t_type, payment_type, amount, message_id, client_id)
            return row['id']

    @staticmethod
    @retry_on_db_error()
    async def get_transactions_for_date(date: datetime.date) -> List[Dict]:
        start = date
        end = date + timedelta(days=1)
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT * FROM transactions
                WHERE created_at >= $1 AND created_at < $2
                ORDER BY created_at
            ''', start, end)
            return [dict(row) for row in rows]

    @staticmethod
    @retry_on_db_error()
    async def get_totals_for_date(date: datetime.date) -> Dict[str, float]:
        start = date
        end = date + timedelta(days=1)
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT payment_type, SUM(amount) as total
                FROM transactions
                WHERE created_at >= $1 AND created_at < $2
                GROUP BY payment_type
            ''', start, end)
            totals = {row['payment_type']: float(row['total']) for row in rows}
            return totals

    @staticmethod
    @retry_on_db_error()
    async def delete_transaction(tx_id: int) -> bool:
        pool = await get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute('DELETE FROM transactions WHERE id = $1', tx_id)
            return result == "DELETE 1"

    @staticmethod
    @retry_on_db_error()
    async def update_transaction_amount(tx_id: int, new_amount: float) -> bool:
        pool = await get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute('''
                UPDATE transactions SET amount = $1, is_corrected = TRUE WHERE id = $2
            ''', new_amount, tx_id)
            return result == "UPDATE 1"

    @staticmethod
    @retry_on_db_error()
    async def delete_old_transactions(days=30):
        cutoff = datetime.now() - timedelta(days=days)
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute('DELETE FROM transactions WHERE created_at < $1', cutoff)

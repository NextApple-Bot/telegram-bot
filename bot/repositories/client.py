# Файл: bot/repositories/client.py
import json
import logging
from datetime import datetime

from bot.db import get_pool, retry_on_db_error

logger = logging.getLogger(__name__)

class ClientRepository:
    """Репозиторий для работы с клиентами и покупками."""

    @staticmethod
    async def get_or_create_client(
        phone: str | None = None,
        phones: list[str] | None = None,
        full_name: str | None = None,
        telegram_username: str | None = None,
        social_network: str | None = None,
        referral_source: str | None = None,
        birth_date: str | None = None,
        conn=None
    ) -> int:
        logger.info(f"🔍 get_or_create_client: phone={phone}, full_name={full_name}, birth_date={birth_date}")

        async def _impl(connection):
            if phone:
                row = await connection.fetchrow(
                    'SELECT id, full_name, telegram_username, social_network, referral_source, phones, birth_date FROM clients WHERE phone = $1',
                    phone
                )
                if row:
                    client_id = row['id']
                    updates = []
                    params = []
                    if full_name and full_name != row['full_name']:
                        updates.append("full_name = $" + str(len(params)+1))
                        params.append(full_name)
                    if telegram_username and telegram_username != row['telegram_username']:
                        updates.append("telegram_username = $" + str(len(params)+1))
                        params.append(telegram_username)
                    if social_network and social_network != row['social_network']:
                        updates.append("social_network = $" + str(len(params)+1))
                        params.append(social_network)
                    if referral_source and referral_source != row['referral_source']:
                        updates.append("referral_source = $" + str(len(params)+1))
                        params.append(referral_source)
                    if phones:
                        existing_phones = row['phones'] if row['phones'] else ""
                        all_phones = set(existing_phones.split(',')) if existing_phones else set()
                        all_phones.update(phones)
                        new_phones_str = ",".join(sorted(all_phones))
                        if new_phones_str != existing_phones:
                            updates.append("phones = $" + str(len(params)+1))
                            params.append(new_phones_str)
                    if birth_date is not None and birth_date != row['birth_date']:
                        updates.append("birth_date = $" + str(len(params)+1))
                        params.append(birth_date)
                    if updates:
                        set_clause = ", ".join(updates)
                        params.append(client_id)
                        query = f"UPDATE clients SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ${len(params)}"  # nosec B608
                        await connection.execute(query, *params)
                        logger.info(f"✅ Клиент {client_id} обновлён")
                    return client_id
                else:
                    phones_str = ",".join(sorted(set(phones))) if phones else None
                    row = await connection.fetchrow('''
                        INSERT INTO clients (full_name, phone, phones, telegram_username, social_network, referral_source, birth_date)
                        VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id
                    ''', full_name, phone, phones_str, telegram_username, social_network, referral_source, birth_date)
                    return row['id']
            else:
                phones_str = ",".join(sorted(set(phones))) if phones else None
                row = await connection.fetchrow('''
                    INSERT INTO clients (full_name, phones, telegram_username, social_network, referral_source, birth_date)
                    VALUES ($1, $2, $3, $4, $5, $6) RETURNING id
                ''', full_name, phones_str, telegram_username, social_network, referral_source, birth_date)
                return row['id']

        if conn is not None:
            return await _impl(conn)
        else:
            pool = await get_pool()
            async with pool.acquire() as new_conn:
                return await _impl(new_conn)

    @staticmethod
    async def add_purchase(
        client_id: int,
        items: list,
        total_amount: float,
        payment_details: dict,
        purchase_type: str = 'sale',
        conn=None
    ):
        items_json = json.dumps(items, ensure_ascii=False)
        payment_json = json.dumps(payment_details, ensure_ascii=False)

        async def _impl(connection):
            await connection.execute('''
                INSERT INTO purchases (client_id, items_json, total_amount, payment_details, purchase_type)
                VALUES ($1, $2, $3, $4, $5)
            ''', client_id, items_json, total_amount, payment_json, purchase_type)

        if conn is not None:
            await _impl(conn)
        else:
            pool = await get_pool()
            async with pool.acquire() as new_conn:
                await _impl(new_conn)

    @staticmethod
    @retry_on_db_error()
    async def get_client_purchases(client_id: int) -> list[dict]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('SELECT * FROM purchases WHERE client_id = $1 ORDER BY created_at DESC', client_id)
            return [dict(row) for row in rows]

    @staticmethod
    @retry_on_db_error()
    async def search_clients(query: str) -> list[dict]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT * FROM clients
                WHERE full_name ILIKE $1 OR phone ILIKE $1 OR telegram_username ILIKE $1
                ORDER BY updated_at DESC
            ''', f'%{query}%')
            return [dict(row) for row in rows]

    @staticmethod
    @retry_on_db_error()
    async def get_available_months() -> list[str]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows1 = await conn.fetch('''
                SELECT DISTINCT to_char(created_at, 'MM.YYYY') as month
                FROM clients
                WHERE created_at IS NOT NULL
            ''')
            rows2 = await conn.fetch('''
                SELECT DISTINCT to_char(created_at, 'MM.YYYY') as month
                FROM purchases
                WHERE created_at IS NOT NULL
            ''')
            months = sorted(set([r['month'] for r in rows1] + [r['month'] for r in rows2]), reverse=True)
            return months

    @staticmethod
    @retry_on_db_error()
    async def get_clients_data_for_month(month_str: str) -> list[dict]:
        month, year = map(int, month_str.split('.'))
        start_date = datetime(year, month, 1).date()
        if month == 12:
            end_date = datetime(year + 1, 1, 1).date()
        else:
            end_date = datetime(year, month + 1, 1).date()

        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT
                    c.id as client_id,
                    c.full_name,
                    c.phone,
                    c.phones,
                    c.telegram_username,
                    c.social_network,
                    c.referral_source,
                    c.birth_date,
                    c.created_at as client_created_at,
                    p.id as purchase_id,
                    p.items_json,
                    p.total_amount,
                    p.payment_details,
                    p.purchase_type,
                    p.created_at as purchase_created_at
                FROM clients c
                LEFT JOIN purchases p ON c.id = p.client_id
                    AND p.created_at >= $1 AND p.created_at < $2
                WHERE (p.id IS NOT NULL) OR (c.created_at >= $1 AND c.created_at < $2)
                ORDER BY c.id, p.created_at
            ''', start_date, end_date)
            return [dict(row) for row in rows]

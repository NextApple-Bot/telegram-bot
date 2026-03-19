from datetime import date
from typing import Dict
from bot.db import get_pool, retry_on_db_error
import logging

logger = logging.getLogger(__name__)

class FinanceRepository:
    """Репозиторий для работы с ежедневными финансовыми сводками."""

    @staticmethod
    @retry_on_db_error()
    async def add_payments(
        cash: float = 0,
        terminal: float = 0,
        qr: float = 0,
        transfer: float = 0,
        invoice: float = 0,
        installment: float = 0,
        bookings_total: float = 0
    ) -> None:
        """
        Добавляет суммы к финансовой записи за текущий день.
        Если записи за сегодня нет, создаёт её.
        
        Args:
            cash: Наличные
            terminal: Терминал
            qr: QR-код
            transfer: Перевод
            invoice: Оплата по счёту
            installment: Рассрочка
            bookings_total: Сумма броней
        """
        today = date.today()
        total = cash + terminal + qr + transfer + invoice + installment + bookings_total

        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO daily_finances (
                    date, cash, terminal, qr, transfer, invoice, installment,
                    bookings_total, total, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, CURRENT_TIMESTAMP)
                ON CONFLICT (date) DO UPDATE SET
                    cash = daily_finances.cash + EXCLUDED.cash,
                    terminal = daily_finances.terminal + EXCLUDED.terminal,
                    qr = daily_finances.qr + EXCLUDED.qr,
                    transfer = daily_finances.transfer + EXCLUDED.transfer,
                    invoice = daily_finances.invoice + EXCLUDED.invoice,
                    installment = daily_finances.installment + EXCLUDED.installment,
                    bookings_total = daily_finances.bookings_total + EXCLUDED.bookings_total,
                    total = daily_finances.total + EXCLUDED.total,
                    updated_at = CURRENT_TIMESTAMP
            ''', today, cash, terminal, qr, transfer, invoice, installment,
                bookings_total, total)

    @staticmethod
    @retry_on_db_error()
    async def get_today() -> Dict[str, float]:
        """Возвращает финансовые данные за сегодня."""
        today = date.today()
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT * FROM daily_finances WHERE date = $1',
                today
            )
            if row:
                return dict(row)
            else:
                return {
                    'date': today,
                    'cash': 0.0,
                    'terminal': 0.0,
                    'qr': 0.0,
                    'transfer': 0.0,
                    'invoice': 0.0,
                    'installment': 0.0,
                    'bookings_total': 0.0,
                    'total': 0.0
                }

    @staticmethod
    @retry_on_db_error()
    async def reset_today() -> None:
        """Удаляет финансовую запись за сегодня (обнуление)."""
        today = date.today()
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'DELETE FROM daily_finances WHERE date = $1',
                today
            )

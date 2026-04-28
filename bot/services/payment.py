# Файл: bot/services/payment.py
import logging

from bot.db import get_pool

logger = logging.getLogger(__name__)


class PaymentService:
    """Централизованное сохранение платежей в daily_payments."""

    @staticmethod
    async def add_payment(payment_type: str, amount: float, source_type: str) -> None:
        """
        Сохраняет один платёж в таблицу daily_payments.

        Args:
            payment_type: 'cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment'
            amount: сумма платежа
            source_type: 'sale' или 'preorder'
        """
        if amount <= 0:
            return
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'INSERT INTO daily_payments (type, payment_type, amount) VALUES ($1, $2, $3)',
                source_type, payment_type, amount
            )
            logger.debug(f"Платёж сохранён: {source_type} {payment_type} = {amount}")

    @staticmethod
    async def add_payments_batch(payments: dict, source_type: str) -> None:
        """
        Сохраняет несколько платежей из словаря.
        payments: {'cash': 100, 'terminal': 200, ...}
        """
        for pay_type, amount in payments.items():
            if amount and amount > 0:
                await PaymentService.add_payment(pay_type, amount, source_type)

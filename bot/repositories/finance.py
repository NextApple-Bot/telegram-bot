from datetime import date
from typing import Dict
from bot.repositories.transaction import TransactionRepository
import logging

logger = logging.getLogger(__name__)

class FinanceRepository:
    @staticmethod
    async def get_today() -> Dict[str, float]:
        today = date.today()
        totals = await TransactionRepository.get_totals_for_date(today)
        return {
            'date': today,
            'cash': totals.get('cash', 0.0),
            'terminal': totals.get('terminal', 0.0),
            'qr': totals.get('qr', 0.0),
            'transfer': totals.get('transfer', 0.0),
            'invoice': totals.get('invoice', 0.0),
            'installment': totals.get('installment', 0.0),
            'bookings_total': 0.0,
            'total': sum(totals.values())
        }

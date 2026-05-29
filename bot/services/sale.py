import logging
from bot.utils.validators import extract_serials
from bot.repositories import ItemRepository, StatsRepository
from bot.services.assortment import AssortmentService
from bot.db import get_pool

logger = logging.getLogger(__name__)


class SaleService:
    @staticmethod
    async def process_sale(content: str, chat_id: int, message_id: int, payments: dict) -> dict:
        serials = list(set(extract_serials(content)))
        is_accessory = len(serials) == 0

        if is_accessory:
            logger.info("[SaleService] Аксессуар — сохраняем только платежи")
            return {
                "sold_items": [],
                "not_found": [],
                "payments": payments,
                "is_accessory": True
            }

        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                sold_items = []
                for serial in serials:
                    item = await ItemRepository.get_item_by_serial(serial)
                    if item:
                        sold_items.append((item['id'], serial))

                if not sold_items:
                    return {
                        "sold_items": [],
                        "not_found": serials,
                        "payments": payments,
                        "is_accessory": False
                    }

                for item_id, serial in sold_items:
                    await AssortmentService.remove_by_serial(serial, reason='sale', conn=conn)

                await StatsRepository.add_sale(
                    count=len(sold_items),
                    cash=payments.get('cash', 0),
                    terminal=payments.get('terminal', 0),
                    qr=payments.get('qr', 0),
                    transfer=payments.get('transfer', 0),
                    invoice=payments.get('invoice', 0),
                    installment=payments.get('installment', 0),
                    is_accessory=False,
                    message_id=message_id,
                    conn=conn
                )

        not_found = [s for s in serials if s not in [x[1] for x in sold_items]]

        return {
            "sold_items": sold_items,
            "not_found": not_found,
            "payments": payments,
            "is_accessory": False
        }

# Файл: bot/services/sale.py
import logging
from bot.repositories import ItemRepository, StatsRepository
from bot.utils.validators import extract_serials
from bot.db import get_pool

logger = logging.getLogger(__name__)


class SaleService:
    @staticmethod
    async def process_sale(content: str, chat_id: int, message_id: int, payments: dict) -> dict:
        serials = list(set(extract_serials(content)))
        is_accessory = (len(serials) == 0)

        if is_accessory:
            logger.info(f"Аксессуар: сохранение только платежей {payments}, продажа не регистрируется.")
            return {
                "sold_items": [],
                "not_found": [],
                "payments": payments,
                "is_accessory": True,
                "skip_sale_stats": True
            }

        pool = await get_pool()
        # Исправлено: объединены with
        async with pool.acquire() as conn, conn.transaction():
            sold_items = []
            for serial in serials:
                item_id = await ItemRepository.get_item_id_by_serial(serial, conn=conn)
                if item_id:
                    sold_items.append((item_id, serial))

            if not sold_items:
                logger.info(f"Серийные номера не найдены: {serials}. Статистика и платежи не сохранены.")
                return {
                    "sold_items": [],
                    "not_found": serials,
                    "payments": payments,
                    "is_accessory": False,
                    "skip_sale_stats": True,
                    "skip_payments": True
                }

            # Удаляем найденные товары
            from .assortment import AssortmentService
            for _item_id, serial in sold_items:  # B007: переименовано в _item_id
                await AssortmentService.remove_by_serial(serial, reason='sale', conn=conn)

            # Сохраняем статистику продажи
            await StatsRepository.add_sale(
                count=len(sold_items),
                cash=payments['cash'],
                terminal=payments['terminal'],
                qr=payments['qr'],
                transfer=payments['transfer'],
                invoice=payments['invoice'],
                installment=payments['installment'],
                is_accessory=False,
                message_id=message_id,
                conn=conn
            )

            not_found = [s for s in serials if s not in [x[1] for x in sold_items]]

            return {
                "sold_items": sold_items,
                "not_found": not_found,
                "payments": payments,
                "is_accessory": False,
                "skip_sale_stats": False,
                "skip_payments": False
            }

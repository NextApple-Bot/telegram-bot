# Файл: bot/services/sale.py
import logging
from bot.repositories import ItemRepository, ClientRepository, StatsRepository
from bot.models import ClientData
from bot.utils.validators import extract_serials
from bot.utils.parser import parse_client_data, extract_payment_amounts
from bot.db import get_pool

logger = logging.getLogger(__name__)


class SaleService:
    @staticmethod
    async def is_message_processed(chat_id: int, message_id: int) -> bool:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT 1 FROM processed_messages WHERE chat_id = $1 AND message_id = $2',
                chat_id, message_id
            )
            return row is not None

    @staticmethod
    async def mark_message_processed(chat_id: int, message_id: int):
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'INSERT INTO processed_messages (chat_id, message_id) VALUES ($1, $2) ON CONFLICT DO NOTHING',
                chat_id, message_id
            )

    @staticmethod
    async def process_sale(content: str, chat_id: int, message_id: int) -> dict:
        """
        Обрабатывает продажу:
        - Если есть серийные номера и они найдены → удаляем товары, сохраняем статистику продаж и платежи.
        - Если серийных номеров нет → это аксессуар → сохраняем только платежи (финансы), статистику продаж НЕ сохраняем.
        - Если серийные номера указаны, но не найдены → ничего не сохраняем.
        """
        if await SaleService.is_message_processed(chat_id, message_id):
            logger.info(f"Сообщение {message_id} уже обработано, пропускаем.")
            return {"sold_items": [], "not_found": [], "payments": {}, "skipped": True}

        payments = extract_payment_amounts(content, ignore_prepay=True)
        serials = list(set(extract_serials(content)))
        is_accessory = (len(serials) == 0)

        # Если это аксессуар (нет серийников) – сохраняем только платежи, статистику продаж не трогаем
        if is_accessory:
            logger.info(f"Аксессуар: сохранение только платежей {payments}, продажа не регистрируется.")
            # Сохраняем платежи в daily_payments (это делает вызывающий код, но для ясности вернём флаг)
            await SaleService.mark_message_processed(chat_id, message_id)
            return {
                "sold_items": [],
                "not_found": [],
                "payments": payments,
                "is_accessory": True,
                "skip_sale_stats": True
            }

        # Если есть серийные номера, проверяем их наличие
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                sold_items = []
                for serial in serials:
                    item_id = await ItemRepository.get_item_id_by_serial(serial, conn=conn)
                    if item_id:
                        sold_items.append((item_id, serial))

                # Если ни один серийник не найден – не сохраняем ничего
                if not sold_items:
                    logger.info(f"Серийные номера не найдены: {serials}. Статистика и платежи не сохранены.")
                    await SaleService.mark_message_processed(chat_id, message_id)
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
                for item_id, serial in sold_items:
                    await AssortmentService.remove_by_serial(serial, reason='sale', conn=conn)

                # Сохраняем статистику продажи (только для найденных товаров)
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
                await SaleService.mark_message_processed(chat_id, message_id)

                return {
                    "sold_items": sold_items,
                    "not_found": not_found,
                    "payments": payments,
                    "is_accessory": False,
                    "skip_sale_stats": False,
                    "skip_payments": False
                }

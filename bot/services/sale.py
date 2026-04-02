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
        from bot.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT 1 FROM processed_messages WHERE chat_id = $1 AND message_id = $2',
                chat_id, message_id
            )
            return row is not None

    @staticmethod
    async def mark_message_processed(chat_id: int, message_id: int):
        from bot.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'INSERT INTO processed_messages (chat_id, message_id) VALUES ($1, $2) ON CONFLICT DO NOTHING',
                chat_id, message_id
            )

    @staticmethod
    async def process_sale(content: str, chat_id: int, message_id: int) -> dict:
        """Обрабатывает продажу: удаляет товары, сохраняет статистику, клиента."""
        if await SaleService.is_message_processed(chat_id, message_id):
            logger.info(f"Сообщение {message_id} уже обработано, пропускаем.")
            return {"sold_items": [], "not_found": [], "payments": {}, "skipped": True}

        payments = extract_payment_amounts(content, ignore_prepay=True)
        serials = list(set(extract_serials(content)))

        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                sold_items = []
                for serial in serials:
                    item_id = await ItemRepository.get_item_id_by_serial(serial, conn=conn)
                    if item_id:
                        sold_items.append((item_id, serial))

                from .assortment import AssortmentService
                for item_id, serial in sold_items:
                    await AssortmentService.remove_by_serial(serial, reason='sale', conn=conn)

                count = len(sold_items)
                is_accessory = (count == 0)
                await StatsRepository.add_sale(
                    count=count,
                    cash=payments['cash'],
                    terminal=payments['terminal'],
                    qr=payments['qr'],
                    transfer=payments['transfer'],
                    invoice=payments['invoice'],
                    installment=payments['installment'],
                    is_accessory=is_accessory,
                    message_id=message_id,
                    conn=conn
                )

        # Сохраняем клиента (вне транзакции, чтобы не держать блокировку долго)
        try:
            data_dict = parse_client_data(content)
            client_data = ClientData(**data_dict)
            if client_data.phones or client_data.full_name:
                client_id = await ClientRepository.get_or_create_client(
                    phone=client_data.main_phone,
                    phones=client_data.phones,
                    full_name=client_data.full_name,
                    telegram_username=client_data.telegram_username,
                    social_network=client_data.social_network,
                    referral_source=client_data.referral_source
                )
                await ClientRepository.add_purchase(
                    client_id=client_id,
                    items=client_data.items,
                    total_amount=client_data.total,
                    payment_details=client_data.payments,
                    purchase_type='sale'
                )
        except Exception as e:
            logger.exception(f"Ошибка при сохранении клиента: {e}")

        await SaleService.mark_message_processed(chat_id, message_id)

        return {
            "sold_items": sold_items,
            "not_found": [s for s in serials if s not in [x[1] for x in sold_items]],
            "payments": payments
        }

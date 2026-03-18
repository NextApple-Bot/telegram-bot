import logging
from bot.repositories import ItemRepository, ClientRepository, StatsRepository, FinanceRepository
from bot.models import ClientData
from bot.utils.validators import extract_serials
from bot.utils.parser import parse_client_data, extract_payment_amounts

logger = logging.getLogger(__name__)

class SaleService:
    @staticmethod
    async def process_sale(content: str, chat_id: int, message_id: int) -> dict:
        """Обрабатывает продажу: удаляет товары, сохраняет статистику, клиента."""
        # 1. Проверка на дубликат (идемпотентность) будет в хендлере

        # 2. Извлечение сумм и серийников
        payments = extract_payment_amounts(content, ignore_prepay=True)
        serials = list(set(extract_serials(content)))

        sold_items = []
        for serial in serials:
            item_id = await ItemRepository.get_item_id_by_serial(serial)
            if item_id:
                sold_items.append((item_id, serial))

        # 3. Удаление товаров (в транзакции через сервис ассортимента)
        from .assortment import AssortmentService
        for item_id, serial in sold_items:
            await AssortmentService.remove_by_serial(serial, reason='sale')

        # 4. Сохранение продажи в статистику
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
            is_accessory=is_accessory
        )

        # 5. Обновление финансов в БД (вместо finances.json)
        await FinanceRepository.add_payments(
            cash=payments['cash'],
            terminal=payments['terminal'],
            qr=payments['qr'],
            transfer=payments['transfer'],
            invoice=payments['invoice'],
            installment=payments['installment']
        )

        # 6. Парсинг и сохранение клиента
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

        return {
            "sold_items": sold_items,
            "not_found": [s for s in serials if s not in [x[1] for x in sold_items]],
            "payments": payments
        }

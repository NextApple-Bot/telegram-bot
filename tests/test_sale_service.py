import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from bot.services.sale import SaleService

@pytest.mark.asyncio
async def test_process_sale_with_serial():
    """Тест обработки продажи с серийным номером."""
    content = "iPhone 15 Pro (ABC123) - 1000₽\nНаличные - 1000"
    chat_id = 123
    message_id = 456

    with patch('bot.services.sale.extract_serials', return_value=["ABC123"]), \
         patch('bot.services.sale.extract_payment_amounts', return_value={
             'cash': 1000, 'terminal': 0, 'qr': 0, 'transfer': 0, 'invoice': 0, 'installment': 0
         }), \
         patch('bot.services.sale.ItemRepository.get_item_id_by_serial', return_value=789), \
         patch('bot.services.sale.AssortmentService.remove_by_serial', new=AsyncMock()) as mock_remove, \
         patch('bot.services.sale.StatsRepository.add_sale', new=AsyncMock()), \
         patch('bot.services.sale.FinanceRepository.add_payments', new=AsyncMock()), \
         patch('bot.services.sale.parse_client_data', return_value={}), \
         patch('bot.services.sale.SaleService.mark_message_processed', new=AsyncMock()):

        result = await SaleService.process_sale(content, chat_id, message_id)

        assert result["sold_items"] == [(789, "ABC123")]
        assert result["not_found"] == []
        mock_remove.assert_called_once_with("ABC123", reason='sale')

@pytest.mark.asyncio
async def test_process_sale_without_serial():
    """Тест обработки продажи без серийного номера (аксессуар)."""
    content = "Чехол - 500₽\nНаличные - 500"
    chat_id = 123
    message_id = 456

    with patch('bot.services.sale.extract_serials', return_value=[]), \
         patch('bot.services.sale.extract_payment_amounts', return_value={
             'cash': 500, 'terminal': 0, 'qr': 0, 'transfer': 0, 'invoice': 0, 'installment': 0
         }), \
         patch('bot.services.sale.StatsRepository.add_sale', new=AsyncMock()) as mock_add_sale, \
         patch('bot.services.sale.FinanceRepository.add_payments', new=AsyncMock()), \
         patch('bot.services.sale.parse_client_data', return_value={}), \
         patch('bot.services.sale.SaleService.mark_message_processed', new=AsyncMock()):

        result = await SaleService.process_sale(content, chat_id, message_id)

        assert result["sold_items"] == []
        mock_add_sale.assert_called_once_with(
            count=0, cash=500, terminal=0, qr=0, transfer=0, invoice=0, installment=0, is_accessory=True
        )

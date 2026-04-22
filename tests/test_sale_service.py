# Файл: tests/test_sale_service.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from bot.services.sale import SaleService


@pytest.mark.asyncio
async def test_process_sale_with_serial():
    """Тест обработки продажи с серийным номером."""
    content = "iPhone 15 Pro (ABC123) - 1000₽\nНаличные - 1000"
    chat_id = 123
    message_id = 456
    payments = {'cash': 1000.0, 'terminal': 0.0, 'qr': 0.0, 'transfer': 0.0, 'invoice': 0.0, 'installment': 0.0}

    with patch('bot.services.sale.extract_serials', return_value=["ABC123"]), \
         patch('bot.services.sale.ItemRepository.get_item_id_by_serial', new=AsyncMock(return_value=789)), \
         patch('bot.services.sale.AssortmentService.remove_by_serial', new=AsyncMock()) as mock_remove, \
         patch('bot.services.sale.StatsRepository.add_sale', new=AsyncMock()), \
         patch('bot.services.sale.get_pool', new=AsyncMock()) as mock_pool:

        # Мокаем пул БД, чтобы транзакция не падала
        mock_conn = AsyncMock()
        mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn

        result = await SaleService.process_sale(content, chat_id, message_id, payments)

        assert result["sold_items"] == [(789, "ABC123")]
        assert result["not_found"] == []
        assert result["is_accessory"] is False
        assert result.get("skip_payments") is False
        mock_remove.assert_called_once_with("ABC123", reason='sale', conn=mock_conn)


@pytest.mark.asyncio
async def test_process_sale_without_serial():
    """Тест обработки продажи без серийного номера (аксессуар)."""
    content = "Чехол - 500₽\nНаличные - 500"
    chat_id = 123
    message_id = 456
    payments = {'cash': 500.0, 'terminal': 0.0, 'qr': 0.0, 'transfer': 0.0, 'invoice': 0.0, 'installment': 0.0}

    with patch('bot.services.sale.extract_serials', return_value=[]), \
         patch('bot.services.sale.get_pool', new=AsyncMock()) as mock_pool:

        mock_conn = AsyncMock()
        mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn

        result = await SaleService.process_sale(content, chat_id, message_id, payments)

        assert result["sold_items"] == []
        assert result["is_accessory"] is True
        assert result.get("skip_sale_stats") is True
        assert result.get("skip_payments") is False


@pytest.mark.asyncio
async def test_process_sale_not_found():
    """Тест: серийные номера указаны, но не найдены в БД."""
    content = "iPhone (XYZ999) - 1000₽\nНаличные - 1000"
    chat_id = 123
    message_id = 456
    payments = {'cash': 1000.0, 'terminal': 0.0, 'qr': 0.0, 'transfer': 0.0, 'invoice': 0.0, 'installment': 0.0}

    with patch('bot.services.sale.extract_serials', return_value=["XYZ999"]), \
         patch('bot.services.sale.ItemRepository.get_item_id_by_serial', new=AsyncMock(return_value=None)), \
         patch('bot.services.sale.get_pool', new=AsyncMock()) as mock_pool:

        mock_conn = AsyncMock()
        mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn

        result = await SaleService.process_sale(content, chat_id, message_id, payments)

        assert result["sold_items"] == []
        assert result["not_found"] == ["XYZ999"]
        assert result.get("skip_sale_stats") is True
        assert result.get("skip_payments") is True

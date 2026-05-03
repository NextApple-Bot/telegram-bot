from unittest.mock import AsyncMock, patch

import pytest

from bot.repositories.client import ClientRepository


@pytest.mark.asyncio
async def test_get_or_create_client_existing_phone():
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = {
        'id': 10,
        'full_name': 'Старое Имя',
        'telegram_username': None,
        'social_network': None,
        'referral_source': None,
        'phones': '',
        'birth_date': None,
    }

    with patch('bot.repositories.client.get_pool') as mock_pool:
        mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn

        client_id = await ClientRepository.get_or_create_client(
            phone='+79991234567',
            full_name='Новое Имя',
            telegram_username='testuser',
            social_network='VK',
            referral_source='Сайт',
            phones=['+79991234567', '+79991112233'],
            birth_date='01.03.1970'
        )

    assert client_id == 10
    mock_conn.execute.assert_called_once()
    update_query = mock_conn.execute.call_args[0][0]
    assert 'UPDATE clients SET' in update_query
    assert mock_conn.fetchrow.called


@pytest.mark.asyncio
async def test_get_or_create_client_new():
    mock_conn = AsyncMock()
    # при поиске клиента не найден
    mock_conn.fetchrow.return_value = None
    # при вставке возвращается id
    mock_conn.fetchrow.return_value = {'id': 20}

    with patch('bot.repositories.client.get_pool') as mock_pool:
        mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn

        client_id = await ClientRepository.get_or_create_client(
            phone='+79991234567',
            full_name='Иван Иванов',
            phones=['+79991234567'],
            birth_date='05.05.1990'
        )

    assert client_id == 20
    assert mock_conn.fetchrow.call_count == 2  # один поиск, один insert


@pytest.mark.asyncio
async def test_search_clients():
    mock_rows = [
        {'id': 1, 'full_name': 'Иван', 'phone': '+7999', 'telegram_username': 'ivan'},
        {'id': 2, 'full_name': 'Петр', 'phone': '+7888', 'telegram_username': 'petr'},
    ]
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = mock_rows

    with patch('bot.repositories.client.get_pool') as mock_pool:
        mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn

        result = await ClientRepository.search_clients('Иван')
    assert len(result) == 2
    assert result[0]['full_name'] == 'Иван'


@pytest.mark.asyncio
async def test_get_client_purchases():
    mock_rows = [{'id': 100, 'total_amount': 15000.0}]
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = mock_rows

    with patch('bot.repositories.client.get_pool') as mock_pool:
        mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
        purchases = await ClientRepository.get_client_purchases(1)

    assert len(purchases) == 1
    assert purchases[0]['total_amount'] == 15000.0


@pytest.mark.asyncio
async def test_add_purchase():
    mock_conn = AsyncMock()
    with patch('bot.repositories.client.get_pool') as mock_pool:
        mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn

        await ClientRepository.add_purchase(
            client_id=1,
            items=[{'item_text': 'iPhone', 'price': 100000}],
            total_amount=100000,
            payment_details={'cash': 100000},
            purchase_type='sale'
        )

    mock_conn.execute.assert_called_once()
    call_args = mock_conn.execute.call_args[0]
    assert 'INSERT INTO purchases' in call_args[0]
    assert call_args[1] == 1  # client_id

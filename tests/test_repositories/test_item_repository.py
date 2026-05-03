import pytest
from unittest.mock import AsyncMock, patch
from bot.repositories.item import ItemRepository


@pytest.mark.asyncio
async def test_get_or_create_category_existing():
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = {'id': 5}

    with patch('bot.repositories.item.get_pool') as mock_pool:
        mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
        cat_id = await ItemRepository.get_or_create_category('iPhone:')

    assert cat_id == 5


@pytest.mark.asyncio
async def test_get_or_create_category_new():
    mock_conn = AsyncMock()
    mock_conn.fetchrow.side_effect = [None, {'id': 10}]
    mock_conn.fetchval.return_value = 0

    with patch('bot.repositories.item.get_pool') as mock_pool:
        mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
        cat_id = await ItemRepository.get_or_create_category('Samsung:')

    assert cat_id == 10


@pytest.mark.asyncio
async def test_add_item():
    mock_conn = AsyncMock()
    with patch('bot.repositories.item.get_pool') as mock_pool, \
         patch.object(ItemRepository, 'get_or_create_category', new=AsyncMock(return_value=3)):
        mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn

        await ItemRepository.add_item(text='iPhone 15', serial='ABC123', category_id=3)
    mock_conn.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_item_id_by_serial():
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = {'id': 7}
    with patch('bot.repositories.item.get_pool') as mock_pool:
        mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
        item_id = await ItemRepository.get_item_id_by_serial('ABC123')
    assert item_id == 7


@pytest.mark.asyncio
async def test_get_item_id_by_serial_not_found():
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = None
    with patch('bot.repositories.item.get_pool') as mock_pool:
        mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
        item_id = await ItemRepository.get_item_id_by_serial('NONEXIST')
    assert item_id is None

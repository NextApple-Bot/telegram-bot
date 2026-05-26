from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select

from bot.db import get_async_session_factory
from bot.models import Seller


class SellerRepository:
    """Репозиторий для работы с продавцами."""

    @staticmethod
    async def create_seller(
        name: str,
        phone: Optional[str] = None,
        telegram_username: Optional[str] = None,
    ) -> Seller | None:
        """Создаёт нового продавца."""
        async with get_async_session_factory()() as session:
            # Проверяем, не существует ли уже продавец с таким именем + телефоном
            existing = await session.execute(
                select(Seller).where(
                    Seller.name == name,
                    Seller.phone == phone,
                )
            )
            if existing.scalar_one_or_none():
                return None  # Уже существует

            seller = Seller(
                name=name,
                phone=phone,
                telegram_username=telegram_username,
                is_active=True,
            )
            session.add(seller)
            await session.commit()
            await session.refresh(seller)
            return seller

    @staticmethod
    async def get_by_telegram_username(username: str) -> Seller | None:
        """Ищет продавца по telegram username."""
        async with get_async_session_factory()() as session:
            result = await session.execute(
                select(Seller).where(Seller.telegram_username == username)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(seller_id: int) -> Seller | None:
        async with get_async_session_factory()() as session:
            return await session.get(Seller, seller_id)

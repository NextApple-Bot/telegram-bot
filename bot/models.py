from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Базовая модель."""
    pass


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    items: Mapped[list["Item"]] = relationship("Item", back_populates="category", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Category {self.id}: {self.name}>"


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    category: Mapped[Category] = relationship("Category", back_populates="items")

    is_booked: Mapped[bool] = mapped_column(Boolean, default=False)
    booking_info: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    serial: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<Item {self.id}: {self.text[:50]}>"


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    telegram_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    social_network: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    referral_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    purchases: Mapped[list["Purchase"]] = relationship("Purchase", back_populates="client", cascade="all, delete-orphan")


class Purchase(Base):
    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    client: Mapped[Client] = relationship("Client", back_populates="purchases")

    total_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    purchase_type: Mapped[str] = mapped_column(String(50), nullable=False)  # sale, preorder, booking
    payment_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    items_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # JSON строкой

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

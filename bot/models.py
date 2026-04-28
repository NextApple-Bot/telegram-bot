# Файл: bot/models.py
from sqlalchemy import (
    Column, Integer, BigInteger, String, Float, Boolean, DateTime,
    ForeignKey, UniqueConstraint, Index, Text, JSON, CheckConstraint, Date
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class Client(Base):
    __tablename__ = 'clients'
    id = Column(Integer, primary_key=True)
    full_name = Column(String)
    phone = Column(String)
    phones = Column(String)
    telegram_username = Column(String)
    social_network = Column(String)
    referral_source = Column(String)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())


class Purchase(Base):
    __tablename__ = 'purchases'
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey('clients.id'), nullable=False)
    items_json = Column(Text)
    total_amount = Column(Float)
    payment_details = Column(JSON)
    purchase_type = Column(String)
    created_at = Column(DateTime, server_default=func.now())


class Category(Base):
    __tablename__ = 'categories'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0, server_default='0')


class Item(Base):
    __tablename__ = 'items'
    id = Column(Integer, primary_key=True)
    text = Column(String, nullable=False)
    serial = Column(String)
    category_id = Column(Integer, ForeignKey('categories.id'))
    is_booked = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    # Поля брони
    booking_price = Column(Float)
    booking_prepayment = Column(Float)
    booking_platform = Column(String)
    booking_full_name = Column(String)
    booking_phone = Column(String)
    booking_payment_type = Column(String)
    # Поля продажи
    sale_price = Column(Float)
    sale_prepayment = Column(Float)
    sale_payment_type = Column(String)
    sale_platform = Column(String)
    sale_full_name = Column(String)
    sale_phone = Column(String)
    sale_payment_amount = Column(Float)
    is_sold = Column(Boolean, default=False)


# Уникальный индекс для серийных номеров (игнорируя NULL)
Item.__table_args__ = (
    Index('idx_items_serial_unique', 'serial', unique=True, postgresql_where=Item.serial.isnot(None)),
)


class Sale(Base):
    __tablename__ = 'sales'
    id = Column(Integer, primary_key=True)
    item_id = Column(Integer)
    count = Column(Integer)
    cash = Column(Float, default=0)
    terminal = Column(Float, default=0)
    qr = Column(Float, default=0)
    transfer = Column(Float, default=0)
    invoice = Column(Float, default=0)
    installment = Column(Float, default=0)
    is_accessory = Column(Boolean, default=False)
    message_id = Column(BigInteger, unique=True)
    sold_at = Column(DateTime, server_default=func.now())


class Preorder(Base):
    __tablename__ = 'preorders'
    id = Column(Integer, primary_key=True)
    cash = Column(Float, default=0)
    terminal = Column(Float, default=0)
    qr = Column(Float, default=0)
    transfer = Column(Float, default=0)
    invoice = Column(Float, default=0)
    installment = Column(Float, default=0)
    created_at = Column(DateTime, server_default=func.now())


class Booking(Base):
    __tablename__ = 'bookings'
    id = Column(Integer, primary_key=True)
    item_id = Column(Integer)
    total_amount = Column(Float)
    booked_at = Column(DateTime, server_default=func.now())


class DailyPayment(Base):
    __tablename__ = 'daily_payments'
    id = Column(Integer, primary_key=True)
    type = Column(String, nullable=False)          # 'sale' or 'preorder'
    payment_type = Column(String, nullable=False)  # cash, terminal, ...
    amount = Column(Float, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    sale_message_id = Column(BigInteger)

    __table_args__ = (
        CheckConstraint("type IN ('sale', 'preorder')", name='type_check'),
        CheckConstraint("payment_type IN ('cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment')", name='payment_type_check'),
        Index('idx_daily_payments_created_at', 'created_at'),
    )


class ProcessedMessage(Base):
    __tablename__ = 'processed_messages'
    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger, nullable=False)
    message_id = Column(Integer, nullable=False)
    processed_at = Column(DateTime, server_default=func.now())
    __table_args__ = (UniqueConstraint('chat_id', 'message_id', name='uq_processed_messages'),)


class DeletedItem(Base):
    __tablename__ = 'deleted_items'
    id = Column(Integer, primary_key=True)
    item_id = Column(Integer)
    text = Column(String)
    serial = Column(String)
    category_id = Column(Integer)
    reason = Column(String)
    restored = Column(Boolean, default=False)
    deleted_at = Column(DateTime, server_default=func.now())
    sale_message_id = Column(BigInteger)


class Seller(Base):
    __tablename__ = 'sellers'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)


class SellerDay(Base):
    __tablename__ = 'seller_days'
    id = Column(Integer, primary_key=True)
    seller_id = Column(Integer, ForeignKey('sellers.id', ondelete='CASCADE'), nullable=False)
    date = Column(Date, nullable=False)
    __table_args__ = (UniqueConstraint('seller_id', 'date', name='uq_seller_date'),)

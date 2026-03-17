from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime

class ClientData(BaseModel):
    full_name: Optional[str] = None
    phones: List[str] = Field(default_factory=list)
    telegram_username: Optional[str] = None
    social_network: Optional[str] = None
    referral_source: Optional[str] = None
    items: List[Dict] = Field(default_factory=list)
    payments: Dict[str, float] = Field(default_factory=dict)
    total: float = 0.0
    main_phone: Optional[str] = None

class Item(BaseModel):
    id: int
    text: str
    serial: Optional[str]
    category_id: int
    category_name: str
    is_booked: bool

class Category(BaseModel):
    id: int
    name: str

class SaleData(BaseModel):
    cash: float = 0.0
    terminal: float = 0.0
    qr: float = 0.0
    transfer: float = 0.0
    invoice: float = 0.0
    installment: float = 0.0
    count: int = 1
    is_accessory: bool = False

class BookingData(BaseModel):
    serial: str
    amount: float
    item_text: str
    category_name: str

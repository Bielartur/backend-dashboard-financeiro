from datetime import datetime, date
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from src.entities.payment import Payment
from decimal import Decimal
from src.entities.payment import PaymentMethod
from src.categories.model import CategoryResponse


class PaymentBase(BaseModel):
    title: str
    date: date
    amount: Decimal
    payment_method: PaymentMethod = PaymentMethod.Pix
    bank_id: UUID


class PaymentCreate(PaymentBase):
    category_id: Optional[UUID] = None


class PaymentUpdate(BaseModel):
    title: Optional[str] = None
    date: Optional[date] = None
    amount: Optional[Decimal] = None
    payment_method: Optional[PaymentMethod] = None
    bank_id: Optional[UUID] = None
    category_id: Optional[UUID] = None


class PaymentResponse(PaymentBase):
    id: UUID
    user_id: UUID
    merchant_id: Optional[UUID] = None
    category: CategoryResponse
    model_config = ConfigDict(from_attributes=True)

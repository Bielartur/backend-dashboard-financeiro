from datetime import datetime, date
from typing import Optional
from uuid import UUID
from pydantic import Field, field_validator
from src.schemas.base import CamelModel
from src.entities.payment import Payment
from decimal import Decimal
from src.entities.payment import PaymentMethod
from src.categories.model import CategoryResponse
from src.merchants.model import MerchantResponse
from src.banks.model import BankResponse


class PaymentMethodSchema(CamelModel):
    value: str
    display_name: str


class PaymentBase(CamelModel):
    title: str
    date: date
    amount: Decimal = Field(decimal_places=2, max_digits=10)
    payment_method: PaymentMethod = PaymentMethod.Pix
    bank_id: UUID


class PaymentCreate(PaymentBase):
    category_id: Optional[UUID] = None


class PaymentUpdate(CamelModel):
    title: Optional[str] = None
    date: Optional[date] = None
    amount: Optional[Decimal] = Field(None, decimal_places=2, max_digits=10)
    payment_method: Optional[PaymentMethod] = None
    bank_id: Optional[UUID] = None
    category_id: Optional[UUID] = None


class PaymentResponse(PaymentBase):
    id: UUID
    user_id: UUID
    merchant_id: Optional[UUID] = None
    merchant: Optional[MerchantResponse] = None
    bank: Optional[BankResponse] = None
    category: CategoryResponse
    payment_method: PaymentMethodSchema

    @field_validator("payment_method", mode="before")
    @classmethod
    def convert_payment_method(cls, v):
        if isinstance(v, PaymentMethod):
            return PaymentMethodSchema(value=v.value, display_name=v.display_name)
        return v

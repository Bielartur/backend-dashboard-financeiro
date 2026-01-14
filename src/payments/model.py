from datetime import datetime, date
from typing import Optional
from uuid import UUID
from enum import Enum
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
    amount: Decimal = Field(decimal_places=2, max_digits=10, ge=0)
    payment_method: Optional[PaymentMethod] = None
    bank_id: UUID


class PaymentCreate(PaymentBase):
    id: Optional[UUID] = None
    category_id: Optional[UUID] = None
    has_merchant: bool = True


class PaymentUpdate(CamelModel):
    title: Optional[str] = None
    date: Optional[datetime] = None
    amount: Optional[Decimal] = Field(None, decimal_places=2, max_digits=10, ge=0)
    payment_method: Optional[PaymentMethod] = None
    bank_id: Optional[UUID] = None
    category_id: Optional[UUID] = None


class PaymentResponse(PaymentBase):
    id: UUID
    user_id: UUID
    merchant_id: Optional[UUID] = None
    has_merchant: bool = True
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


class ImportSource(str, Enum):
    NUBANK = "nubank"
    ITAU = "itau"


class ImportType(str, Enum):
    CREDIT_CARD_INVOICE = "invoice"
    BANK_STATEMENT = "statement"


class PaymentImportResponse(CamelModel):
    id: Optional[UUID] = None
    date: date
    title: str
    amount: Decimal
    category: Optional[CategoryResponse] = None
    has_merchant: bool = True
    already_exists: bool = False
    payment_method: Optional[PaymentMethodSchema] = None

    @field_validator("payment_method", mode="before")
    @classmethod
    def convert_payment_method(cls, v):
        # Already a schema?
        if isinstance(v, dict) and "value" in v and "display_name" in v:
            return v

        # Is it an ID string? (not expected for import response but possible)
        if isinstance(v, str):
            try:
                v = PaymentMethod(v)
            except ValueError:
                return None

        # Convert Enum to Schema
        if isinstance(v, PaymentMethod):
            return PaymentMethodSchema(value=v.value, display_name=v.display_name)

        return v

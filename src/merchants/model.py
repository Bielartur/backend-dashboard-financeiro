from datetime import datetime
from typing import Optional, List
from uuid import UUID
from src.schemas.base import CamelModel


class MerchantBase(CamelModel):
    name: str
    category_id: Optional[UUID] = None


class MerchantCreate(MerchantBase):
    merchant_alias_id: Optional[UUID] = None


class MerchantUpdate(CamelModel):
    name: Optional[str] = None
    category_id: Optional[UUID] = None
    merchant_alias_id: Optional[UUID] = None


class MerchantResponse(MerchantBase):
    id: UUID
    merchant_alias_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

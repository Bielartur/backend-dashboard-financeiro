from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class MerchantBase(BaseModel):
    name: str
    category_id: Optional[UUID] = None


class MerchantCreate(MerchantBase):
    pass


class MerchantUpdate(BaseModel):
    name: Optional[str] = None
    category_id: Optional[UUID] = None


class MerchantResponse(MerchantBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MerchantAliasBase(BaseModel):
    pattern: str
    merchant_id: UUID


class MerchantAliasCreate(MerchantAliasBase):
    pass


class MerchantAliasUpdate(BaseModel):
    pattern: Optional[str] = None
    merchant_id: Optional[UUID] = None


class MerchantAliasResponse(MerchantAliasBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

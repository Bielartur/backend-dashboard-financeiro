from datetime import datetime
from typing import Optional, List
from uuid import UUID
from src.schemas.base import CamelModel
from src.merchants.model import MerchantResponse


class MerchantAliasBase(CamelModel):
    pattern: str
    merchant_ids: List[UUID]
    category_id: Optional[UUID] = None


class MerchantAliasCreate(MerchantAliasBase):
    pass


class MerchantAliasUpdate(CamelModel):
    pattern: Optional[str] = None
    merchant_ids: Optional[List[UUID]] = None
    category_id: Optional[UUID] = None


class MerchantAliasMerge(CamelModel):
    pattern: str
    alias_ids: List[UUID]


class MerchantAliasResponse(MerchantAliasBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class MerchantAliasDetailResponse(MerchantAliasResponse):
    merchants: List[MerchantResponse]

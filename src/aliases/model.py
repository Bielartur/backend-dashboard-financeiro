from datetime import datetime
from typing import Optional, List
from uuid import UUID
from src.schemas.base import CamelModel
from src.merchants.model import MerchantResponse


class MerchantAliasBase(CamelModel):
    pattern: str
    merchant_ids: List[UUID]
    category_id: Optional[UUID] = None
    is_investment: bool = False
    ignored: bool = False
    update_past_transactions: bool = True


class MerchantAliasCreate(MerchantAliasBase):
    merchant_ids: Optional[List[UUID]] = []


class MerchantAliasUpdate(CamelModel):
    pattern: Optional[str] = None
    merchant_ids: Optional[List[UUID]] = None
    category_id: Optional[UUID] = None
    is_investment: Optional[bool] = None
    ignored: Optional[bool] = None
    update_past_transactions: Optional[bool] = True


class MerchantAliasMerge(CamelModel):
    pattern: str
    alias_ids: List[UUID]


class MerchantAliasResponse(MerchantAliasBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class MerchantAliasDetailResponse(MerchantAliasResponse):
    merchants: List[MerchantResponse]

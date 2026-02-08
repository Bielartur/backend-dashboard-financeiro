from datetime import datetime
from uuid import UUID
from typing import Optional, List, Dict, Any
from enum import Enum

from pydantic import BaseModel, ConfigDict
from src.schemas.base import CamelModel
from src.entities.open_finance_item import ItemStatus


class CreateItemRequest(CamelModel):
    item_id: str
    connector_id: int


class AccountSummary(CamelModel):
    id: str
    name: str
    number: Optional[str] = None
    type: str
    balance: float


class ItemResponse(CamelModel):
    id: str
    pluggy_item_id: str
    bank_name: str
    status: str
    logo_url: Optional[str] = None
    color_hex: Optional[str] = None
    accounts: List[AccountSummary] = []


class ConnectTokenResponse(CamelModel):
    access_token: str


class OpenFinanceTransaction(CamelModel):
    id: str
    description: str
    amount: float
    date: str
    currency_code: str = "BRL"
    type: str  # CREDIT vs DEBIT
    category_id: Optional[str] = None
    account_name: Optional[str] = None
    account_number: Optional[str] = None


class SyncResponse(CamelModel):
    message: str


class SyncProgressResponse(CamelModel):
    status: str
    message: str

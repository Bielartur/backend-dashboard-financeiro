from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import constr
from src.schemas.base import CamelModel


class BankBase(CamelModel):
    name: str
    slug: Optional[str] = None
    logo_url: str
    color_hex: constr(pattern=r"^#[0-9A-Fa-f]{6}$")


class BankCreate(BankBase):
    pass


class BankUpdate(CamelModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    logo_url: Optional[str] = None
    color_hex: Optional[constr(pattern=r"^#[0-9A-Fa-f]{6}$")] = None


class BankResponse(BankBase):
    id: UUID
    is_active: bool = True

    created_at: datetime
    updated_at: datetime

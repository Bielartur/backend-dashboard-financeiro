from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, constr


class BankBase(BaseModel):
    name: str
    slug: str
    is_active: bool = True
    logo_url: str
    color_hex: constr(pattern=r"^#[0-9A-Fa-f]{6}$")  # Validação de cor hex


class BankCreate(BankBase):
    pass


class BankUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    is_active: Optional[bool] = None
    logo_url: Optional[str] = None
    color_hex: Optional[constr(pattern=r"^#[0-9A-Fa-f]{6}$")] = None


class BankResponse(BankBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

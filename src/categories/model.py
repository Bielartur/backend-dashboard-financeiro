from datetime import datetime
from typing import Optional
from uuid import UUID
from src.schemas.base import CamelModel
from decimal import Decimal
from src.entities.category import Category
from pydantic import constr


class CategoryBase(CamelModel):
    name: str
    color_hex: constr(pattern=r"^#[0-9A-Fa-f]{6}$")  # Validação de cor hex
    is_investment: bool = False
    ignored: bool = False


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(CategoryBase):
    name: Optional[str] = None
    color_hex: Optional[constr(pattern=r"^#[0-9A-Fa-f]{6}$")] = None
    is_investment: Optional[bool] = None
    ignored: Optional[bool] = None


class CategorySettingsUpdate(CamelModel):
    alias: Optional[str] = None
    color_hex: Optional[constr(pattern=r"^#[0-9A-Fa-f]{6}$")] = None
    is_investment: Optional[bool] = None
    ignored: Optional[bool] = None


class CategoryResponse(CategoryBase):
    id: UUID
    alias: Optional[str] = None
    slug: str

    created_at: datetime
    updated_at: datetime


class CategorySimpleResponse(CategoryBase):
    id: UUID
    slug: str

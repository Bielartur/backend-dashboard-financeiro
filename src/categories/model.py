from datetime import datetime
from typing import Optional
from uuid import UUID
from src.schemas.base import CamelModel
from decimal import Decimal
from src.entities.category import Category, CategoryType
from pydantic import constr


class CategoryBase(CamelModel):
    name: str
    color_hex: constr(pattern=r"^#[0-9A-Fa-f]{6}$")  # Validação de cor hex
    type: CategoryType = CategoryType.EXPENSE


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(CategoryBase):
    name: Optional[str] = None
    color_hex: Optional[constr(pattern=r"^#[0-9A-Fa-f]{6}$")] = None
    type: Optional[CategoryType] = None


class CategoryColorUpdate(CamelModel):
    color_hex: constr(pattern=r"^#[0-9A-Fa-f]{6}$")


class CategoryResponse(CategoryBase):
    id: UUID
    slug: str

    created_at: datetime
    updated_at: datetime

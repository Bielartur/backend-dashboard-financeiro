from datetime import datetime
from typing import Optional
from uuid import UUID
from src.schemas.base import CamelModel
from decimal import Decimal
from src.entities.category import Category
from pydantic import constr


class CategoryBase(CamelModel):
    name: str
    slug: str
    color_hex: constr(pattern=r"^#[0-9A-Fa-f]{6}$")  # Validação de cor hex


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(CategoryBase):
    name: Optional[str] = None
    slug: Optional[str] = None
    color_hex: Optional[constr(pattern=r"^#[0-9A-Fa-f]{6}$")] = None


class CategoryResponse(CategoryBase):
    id: UUID

    created_at: datetime
    updated_at: datetime

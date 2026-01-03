from datetime import datetime
from typing import Optional
from uuid import UUID
from src.schemas.base import CamelModel
from decimal import Decimal
from src.entities.category import Category


class CategoryBase(CamelModel):
    name: str


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(CategoryBase):
    name: Optional[str] = None


class CategoryResponse(CategoryBase):
    id: UUID

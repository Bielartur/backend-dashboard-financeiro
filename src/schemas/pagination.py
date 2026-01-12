from typing import Generic, TypeVar, List
from pydantic import Field
from .base import CamelModel

T = TypeVar("T")


class PaginatedResponse(CamelModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    size: int
    pages: int

    @classmethod
    def create(cls, items: List[T], total: int, page: int, size: int):
        import math

        pages = math.ceil(total / size) if size > 0 else 0
        return cls(items=items, total=total, page=page, size=size, pages=pages)

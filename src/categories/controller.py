from fastapi import APIRouter, status
from typing import List
from uuid import UUID

from ..database.core import DbSession
from . import model
from . import service
from ..auth.service import CurrentUser

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.post(
    "/", response_model=model.CategoryResponse, status_code=status.HTTP_201_CREATED
)
async def create_category(
    db: DbSession, category: model.CategoryCreate, current_user: CurrentUser
):
    return service.create_category(current_user, db, category)


@router.get("/", response_model=List[model.CategoryResponse])
async def get_categories(db: DbSession, current_user: CurrentUser):
    return service.get_categories(current_user, db)


@router.get("/{category_id}", response_model=model.CategoryResponse)
async def get_category(db: DbSession, category_id: UUID, current_user: CurrentUser):
    return service.get_category_by_id(current_user, db, category_id)


@router.put("/{category_id}", response_model=model.CategoryResponse)
async def update_category(
    db: DbSession,
    category_id: UUID,
    category_update: model.CategoryUpdate,
    current_user: CurrentUser,
):
    return service.update_category(current_user, db, category_id, category_update)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(db: DbSession, category_id: UUID, current_user: CurrentUser):
    return service.delete_category(current_user, db, category_id)

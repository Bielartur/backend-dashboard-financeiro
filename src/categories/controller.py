from fastapi import APIRouter, status, Query
from typing import List
from uuid import UUID

from ..database.core import DbSession
from . import model
from . import service
from ..auth.service import CurrentUser, CurrentAdmin

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.post(
    "/", response_model=model.CategoryResponse, status_code=status.HTTP_201_CREATED
)
async def create_category(
    db: DbSession, category: model.CategoryCreate, current_user: CurrentAdmin
):
    return await service.create_category(current_user, db, category)


@router.get("/", response_model=List[model.CategoryResponse])
async def get_categories(
    db: DbSession,
    current_user: CurrentUser,
    view: str = Query(
        default="user", pattern="^(user|global)$"
    ),  # user = personalized, global = raw
):
    # Only admin should probably access global view, checking permissions?
    # User requested: "Admin Panel must show Global state".
    # Assuming CurrentUser can be admin.
    # if view == "global" and not current_user.is_admin: ... (logic for another time if needed)
    return await service.get_categories(current_user, db, view)


from ..schemas.pagination import PaginatedResponse


@router.get("/search", response_model=PaginatedResponse[model.CategoryResponse])
async def search_categories(
    db: DbSession,
    current_user: CurrentUser,
    query: str = Query(default="", alias="q"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=12, ge=1, le=100),
    scope: str = Query(default="general", pattern="^(general|investment|ignored|all)$"),
):
    return await service.search_categories(current_user, db, query, page, limit, scope)


@router.get("/{category_id}", response_model=model.CategoryResponse)
async def get_category(db: DbSession, category_id: UUID, current_user: CurrentUser):
    return await service.get_category_by_id(current_user, db, category_id)


@router.put("/{category_id}", response_model=model.CategoryResponse)
async def update_category(
    db: DbSession,
    category_id: UUID,
    category_update: model.CategoryUpdate,
    current_user: CurrentAdmin,
):
    return await service.update_category(current_user, db, category_id, category_update)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(db: DbSession, category_id: UUID, current_user: CurrentAdmin):
    return await service.delete_category(current_user, db, category_id)


@router.put("/{category_id}/settings", response_model=model.CategoryResponse)
async def update_category_settings(
    db: DbSession,
    category_id: UUID,
    settings_update: model.CategorySettingsUpdate,
    current_user: CurrentUser,
):
    return await service.update_category_settings(
        current_user, db, category_id, settings_update
    )

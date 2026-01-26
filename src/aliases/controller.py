from fastapi import APIRouter, status, Depends
from typing import List
from uuid import UUID

from ..database.core import DbSession
from . import model
from . import service
from ..auth.service import get_current_user
from ..auth.model import TokenData

from ..schemas.pagination import PaginatedResponse

router = APIRouter(prefix="/aliases", tags=["Merchant Aliases"])


@router.get("/", response_model=PaginatedResponse[model.MerchantAliasResponse])
async def get_merchant_aliases(
    page: int = 1,
    size: int = 20,
    db: DbSession = None,  # Fix: DbSession is usually not default None but Depends? Checking file... it was positional `db: DbSession`.
    current_user: TokenData = Depends(get_current_user),
):
    # Re-checking DbSession usage in original file.
    # It was: db: DbSession, current_user: TokenData...
    return service.get_merchant_aliases(current_user, db, page, size)


@router.get("/search", response_model=PaginatedResponse[model.MerchantAliasResponse])
async def search_aliases(
    query: str,
    page: int = 1,
    size: int = 20,
    db: DbSession = None,
    current_user: TokenData = Depends(get_current_user),
):
    return service.search_merchants_by_alias(current_user, db, query, page, size)


@router.get("/{alias_id}", response_model=model.MerchantAliasDetailResponse)
async def get_merchant_alias(
    db: DbSession, alias_id: UUID, current_user: TokenData = Depends(get_current_user)
):
    return service.get_alias_by_id(current_user, db, alias_id)


@router.put("/{alias_id}", response_model=model.MerchantAliasResponse)
def update_merchant_alias(
    db: DbSession,
    alias_id: UUID,
    alias_update: model.MerchantAliasUpdate,
    current_user: TokenData = Depends(get_current_user),
):
    return service.update_merchant_alias(current_user, db, alias_id, alias_update)


@router.post(
    "/set_group",
    response_model=model.MerchantAliasResponse,
    status_code=status.HTTP_200_OK,
)
def create_merchant_alias_group(
    db: DbSession,
    alias_group: model.MerchantAliasCreate,
    current_user: TokenData = Depends(get_current_user),
):
    return service.create_merchant_alias_group(current_user, db, alias_group)


@router.post(
    "/{alias_id}/append/{merchant_id}",
    response_model=model.MerchantAliasResponse,
    status_code=status.HTTP_201_CREATED,
)
async def append_merchant_to_alias(
    db: DbSession,
    alias_id: UUID,
    merchant_id: UUID,
    current_user: TokenData = Depends(get_current_user),
):
    return service.append_merchant_to_alias(current_user, db, alias_id, merchant_id)


@router.delete(
    "/{alias_id}/remove/{merchant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_merchant_from_alias(
    db: DbSession,
    alias_id: UUID,
    merchant_id: UUID,
    current_user: TokenData = Depends(get_current_user),
):
    return service.remove_merchant_from_alias(current_user, db, alias_id, merchant_id)

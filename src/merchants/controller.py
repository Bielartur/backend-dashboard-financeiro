from fastapi import APIRouter, status, Depends
from typing import List
from uuid import UUID

from ..database.core import DbSession
from . import model
from . import service
from ..auth.service import get_current_user
from ..auth.model import TokenData
from src.aliases import model as alias_model

router = APIRouter(prefix="/merchants", tags=["Merchants"])


# Merchant endpoints
@router.post(
    "/", response_model=model.MerchantResponse, status_code=status.HTTP_201_CREATED
)
async def create_merchant(
    db: DbSession,
    merchant: model.MerchantCreate,
    current_user: TokenData = Depends(get_current_user),
):
    return service.create_merchant(current_user, db, merchant)


@router.get("/", response_model=List[model.MerchantResponse])
async def get_merchants(
    db: DbSession, current_user: TokenData = Depends(get_current_user)
):
    return service.get_merchants(current_user, db)


@router.get("/search", response_model=List[model.MerchantResponse])
async def search_merchants(
    query: str,
    db: DbSession,
    limit: int = 12,
    current_user: TokenData = Depends(get_current_user),
):
    return service.search_merchants(current_user, db, query, limit)


@router.get("/{merchant_id}", response_model=model.MerchantResponse)
async def get_merchant(
    db: DbSession,
    merchant_id: UUID,
    current_user: TokenData = Depends(get_current_user),
):
    return service.get_merchant_by_id(current_user, db, merchant_id)


@router.put("/{merchant_id}", response_model=model.MerchantResponse)
async def update_merchant(
    db: DbSession,
    merchant_id: UUID,
    merchant_update: model.MerchantUpdate,
    current_user: TokenData = Depends(get_current_user),
):
    return service.update_merchant(current_user, db, merchant_id, merchant_update)


@router.delete("/{merchant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_merchant(
    db: DbSession,
    merchant_id: UUID,
    current_user: TokenData = Depends(get_current_user),
):
    return service.delete_merchant(current_user, db, merchant_id)

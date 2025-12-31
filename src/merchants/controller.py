from fastapi import APIRouter, status
from typing import List
from uuid import UUID

from ..database.core import DbSession
from . import model
from . import service

router = APIRouter(prefix="/merchants", tags=["Merchants"])


# Merchant endpoints
@router.post(
    "/", response_model=model.MerchantResponse, status_code=status.HTTP_201_CREATED
)
async def create_merchant(db: DbSession, merchant: model.MerchantCreate):
    return service.create_merchant(db, merchant)


@router.get("/", response_model=List[model.MerchantResponse])
async def get_merchants(db: DbSession):
    return service.get_merchants(db)


@router.get("/{merchant_id}", response_model=model.MerchantResponse)
async def get_merchant(db: DbSession, merchant_id: UUID):
    return service.get_merchant_by_id(db, merchant_id)


@router.put("/{merchant_id}", response_model=model.MerchantResponse)
async def update_merchant(
    db: DbSession, merchant_id: UUID, merchant_update: model.MerchantUpdate
):
    return service.update_merchant(db, merchant_id, merchant_update)


@router.delete("/{merchant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_merchant(db: DbSession, merchant_id: UUID):
    return service.delete_merchant(db, merchant_id)


# Merchant Alias endpoints
@router.post(
    "/{merchant_id}/aliases",
    response_model=model.MerchantAliasResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_merchant_alias(
    db: DbSession, merchant_id: UUID, alias: model.MerchantAliasCreate
):
    return service.create_merchant_alias(db, alias)


@router.get("/{merchant_id}/aliases", response_model=List[model.MerchantAliasResponse])
async def get_merchant_aliases(db: DbSession, merchant_id: UUID):
    return service.get_aliases_by_merchant(db, merchant_id)


@router.delete("/aliases/{alias_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_merchant_alias(db: DbSession, alias_id: UUID):
    return service.delete_merchant_alias(db, alias_id)

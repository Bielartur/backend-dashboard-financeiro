from fastapi import APIRouter, status, Depends
from typing import List
from uuid import UUID

from ..database.core import DbSession
from . import model
from . import service
from ..auth.service import get_current_user, CurrentAdmin
from ..auth.model import TokenData

router = APIRouter(prefix="/banks", tags=["Banks"])


@router.post(
    "/", response_model=model.BankResponse, status_code=status.HTTP_201_CREATED
)
async def create_bank(
    db: DbSession,
    bank: model.BankCreate,
    current_user: CurrentAdmin,
):
    return service.create_bank(current_user, db, bank)


@router.get("/", response_model=List[model.BankResponse])
async def get_banks(db: DbSession, current_user: TokenData = Depends(get_current_user)):
    return service.get_banks(current_user, db)


@router.get("/{bank_id}", response_model=model.BankResponse)
async def get_bank(
    db: DbSession, bank_id: UUID, current_user: TokenData = Depends(get_current_user)
):
    return service.get_bank_by_id(current_user, db, bank_id)


@router.put("/{bank_id}", response_model=model.BankResponse)
async def update_bank(
    db: DbSession,
    bank_id: UUID,
    bank_update: model.BankUpdate,
    current_user: CurrentAdmin,
):
    return service.update_bank(current_user, db, bank_id, bank_update)


@router.delete("/{bank_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bank(db: DbSession, bank_id: UUID, current_user: CurrentAdmin):
    return service.delete_bank(current_user, db, bank_id)

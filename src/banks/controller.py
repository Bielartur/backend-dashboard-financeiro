from fastapi import APIRouter, status
from typing import List
from uuid import UUID

from ..database.core import DbSession
from . import model
from . import service

router = APIRouter(prefix="/banks", tags=["Banks"])


@router.post(
    "/", response_model=model.BankResponse, status_code=status.HTTP_201_CREATED
)
async def create_bank(db: DbSession, bank: model.BankCreate):
    return service.create_bank(db, bank)


@router.get("/", response_model=List[model.BankResponse])
async def get_banks(db: DbSession):
    return service.get_banks(db)


@router.get("/{bank_id}", response_model=model.BankResponse)
async def get_bank(db: DbSession, bank_id: UUID):
    return service.get_bank_by_id(db, bank_id)


@router.put("/{bank_id}", response_model=model.BankResponse)
async def update_bank(db: DbSession, bank_id: UUID, bank_update: model.BankUpdate):
    return service.update_bank(db, bank_id, bank_update)


@router.delete("/{bank_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bank(db: DbSession, bank_id: UUID):
    return service.delete_bank(db, bank_id)

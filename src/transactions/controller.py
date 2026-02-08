from fastapi import UploadFile, File, APIRouter, status
from typing import List, Optional
from uuid import UUID
from datetime import date
from decimal import Decimal

from ..database.core import DbSession
from . import model
from . import service
from ..auth.service import CurrentUser
from src.schemas.pagination import PaginatedResponse


router = APIRouter(prefix="/transactions", tags=["Transactions"])


@router.post(
    "/", response_model=model.TransactionResponse, status_code=status.HTTP_201_CREATED
)
async def create_transaction(
    db: DbSession, transaction: model.TransactionCreate, current_user: CurrentUser
):
    return service.create_transaction(current_user, db, transaction)


@router.post(
    "/bulk",
    response_model=List[model.TransactionResponse],
    status_code=status.HTTP_201_CREATED,
)
def bulk_create_transaction(
    db: DbSession,
    transactions: List[model.TransactionCreate],
    current_user: CurrentUser,
    import_type: Optional[model.ImportType] = None,
):
    return service.bulk_create_transaction(current_user, db, transactions, import_type)


@router.get("/search", response_model=PaginatedResponse[model.TransactionResponse])
async def search_transactions(
    db: DbSession,
    current_user: CurrentUser,
    query: Optional[str] = None,
    page: int = 1,
    limit: int = 12,
    payment_method: Optional[str] = None,
    category_id: Optional[UUID] = None,
    bank_id: Optional[UUID] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    min_amount: Optional[Decimal] = None,
    max_amount: Optional[Decimal] = None,
):
    return service.search_transactions(
        current_user,
        db,
        query,
        page,
        limit,
        payment_method,
        category_id,
        bank_id,
        start_date,
        end_date,
        min_amount,
        max_amount,
    )


@router.get("/{transaction_id}", response_model=model.TransactionResponse)
async def get_transaction(
    db: DbSession, transaction_id: UUID, current_user: CurrentUser
):
    return service.get_transaction_by_id(current_user, db, transaction_id)


@router.put("/{transaction_id}", response_model=model.TransactionResponse)
async def update_transaction(
    db: DbSession,
    transaction_id: UUID,
    transaction_update: model.TransactionUpdate,
    current_user: CurrentUser,
):
    return service.update_transaction(
        current_user, db, transaction_id, transaction_update
    )


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    db: DbSession, transaction_id: UUID, current_user: CurrentUser
):
    return service.delete_transaction(current_user, db, transaction_id)


@router.post("/import/{source}", response_model=List[model.TransactionImportResponse])
async def import_transactions(
    source: model.ImportSource,
    type: model.ImportType = model.ImportType.CREDIT_CARD_INVOICE,
    file: UploadFile = File(...),
    db: DbSession = DbSession,
    current_user: CurrentUser = CurrentUser,
):
    return await service.import_transactions_from_csv(
        current_user, db, file, source, type
    )

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


router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post(
    "/", response_model=model.PaymentResponse, status_code=status.HTTP_201_CREATED
)
async def create_payment(
    db: DbSession, payment: model.PaymentCreate, current_user: CurrentUser
):
    return service.create_payment(current_user, db, payment)


@router.post(
    "/bulk",
    response_model=List[model.PaymentResponse],
    status_code=status.HTTP_201_CREATED,
)
async def bulk_create_payment(
    db: DbSession,
    payments: List[model.PaymentCreate],
    current_user: CurrentUser,
    import_type: Optional[model.ImportType] = None,
):
    return service.bulk_create_payment(current_user, db, payments, import_type)


@router.get("/search", response_model=PaginatedResponse[model.PaymentResponse])
def search_payments(
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
    return service.search_payments(
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


@router.get("/{payment_id}", response_model=model.PaymentResponse)
async def get_payment(db: DbSession, payment_id: UUID, current_user: CurrentUser):
    return service.get_payment_by_id(current_user, db, payment_id)


@router.put("/{payment_id}", response_model=model.PaymentResponse)
async def update_payment(
    db: DbSession,
    payment_id: UUID,
    payment_update: model.PaymentUpdate,
    current_user: CurrentUser,
):
    return service.update_payment(current_user, db, payment_id, payment_update)


@router.delete("/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payment(db: DbSession, payment_id: UUID, current_user: CurrentUser):
    return service.delete_payment(current_user, db, payment_id)


@router.post("/import/{source}", response_model=List[model.PaymentImportResponse])
async def import_payments(
    source: model.ImportSource,
    type: model.ImportType = model.ImportType.CREDIT_CARD_INVOICE,
    file: UploadFile = File(...),
    db: DbSession = DbSession,
    current_user: CurrentUser = CurrentUser,
):
    return await service.import_payments_from_csv(current_user, db, file, source, type)

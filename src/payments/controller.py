from fastapi import APIRouter, status
from typing import List
from uuid import UUID

from ..database.core import DbSession
from . import model
from . import service
from ..auth.service import CurrentUser

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post(
    "/", response_model=model.PaymentResponse, status_code=status.HTTP_201_CREATED
)
async def create_payment(
    db: DbSession, payment: model.PaymentCreate, current_user: CurrentUser
):
    return service.create_payment(current_user, db, payment)


@router.get("/", response_model=List[model.PaymentResponse])
async def get_payments(db: DbSession, current_user: CurrentUser):
    return service.get_payments(current_user, db)


@router.get("/{payment_id}", response_model=model.PaymentResponse)
async def get_payment(db: DbSession, payment_id: UUID, current_user: CurrentUser):
    return service.get_payment_by_id(current_user, db, payment_id)


@router.put("/{payment_id}", response_model=model.PaymentResponse)
async def update_payment(db: DbSession, payment_id: UUID, current_user: CurrentUser):
    return service.update_payment(current_user, db, payment_id)


@router.delete("/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payment(db: DbSession, payment_id: UUID, current_user: CurrentUser):
    return service.delete_payment(current_user, db, payment_id)

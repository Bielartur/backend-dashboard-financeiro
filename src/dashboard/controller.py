from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from src.database.core import get_db
from src.auth.service import get_current_user
from src.dashboard import model, service

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/available-months", response_model=List[model.DashboardAvailableMonth])
def get_available_months(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    return service.get_available_months(db, current_user.get_uuid())


@router.get("/", response_model=model.DashboardResponse)
def dashboard_data(
    year: str = Query("last-12", description="Year (e.g. 2024) or 'last-12'"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):

    return service.get_dashboard_data(db, current_user.get_uuid(), year)

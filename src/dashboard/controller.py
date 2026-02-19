from typing import List
from fastapi import APIRouter, Depends, Query
from src.database.core import DbSession
from src.auth.service import get_current_user
from src.dashboard import model, service

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/available-months", response_model=List[model.DashboardAvailableMonth])
async def get_available_months(
    db: DbSession,
    current_user=Depends(get_current_user),
):
    return await service.get_available_months(db, current_user.get_uuid())


@router.get("/", response_model=model.DashboardResponse)
async def dashboard_data(
    year: str = Query("last-12", description="Year (e.g. 2024) or 'last-12'"),
    group_by: str = Query(
        "category", description="Grouping method: category, merchant, bank"
    ),
    current_user=Depends(get_current_user),
    db: DbSession = Depends,  # Fixed type checking
):
    return await service.get_dashboard_data(db, current_user.get_uuid(), year, group_by)

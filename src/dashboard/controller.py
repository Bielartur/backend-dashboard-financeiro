from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from src.database.core import get_db
from src.auth.service import get_current_user
from src.dashboard.model import DashboardResponse

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/", response_model=DashboardResponse)
def dashboard_data(
    year: str = Query("last-12", description="Year (e.g. 2024) or 'last-12'"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from src.dashboard.service import get_dashboard_data

    return get_dashboard_data(db, current_user.user_id, year)

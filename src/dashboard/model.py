from decimal import Decimal
from typing import List, Optional, Literal
from src.schemas.base import CamelModel
from src.entities.transaction import TransactionType


class DashboardSummary(CamelModel):
    total_revenue: Decimal
    total_expenses: Decimal
    balance: Decimal
    total_investments: Decimal = Decimal(0)


class DashboardAvailableMonth(CamelModel):
    year: Optional[int] = None
    month: Optional[int] = None
    value: Optional[str] = None
    label: str


class DashboardMetric(CamelModel):
    id: str  # UUID or Slug
    name: str
    description: Optional[str] = None
    color_hex: str
    logo_url: Optional[str] = None
    type: TransactionType
    total: Decimal
    average: Optional[Decimal] = Decimal(0)
    # Status is mostly relevant for Categories, but we keep it for compatibility
    status: Literal["above_average", "below_average", "average", "unknown"] = "unknown"
    # IDs grouped into "Outros" (only populated for the Others metric)
    grouped_ids: Optional[List[str]] = None


class MonthlyData(CamelModel):
    month: str
    month_short: str
    year: int
    revenue: Decimal
    expenses: Decimal
    investments: Decimal = Decimal(0)
    balance: Decimal
    # Generic metrics (could be categories, banks, or merchants)
    metrics: List[DashboardMetric]


class DashboardResponse(CamelModel):
    summary: DashboardSummary
    months: List[MonthlyData]


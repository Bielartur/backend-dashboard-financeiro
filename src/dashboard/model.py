from decimal import Decimal
from typing import List, Optional, Literal
from src.schemas.base import CamelModel
from src.entities.category import CategoryType


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


class CategoryMetric(CamelModel):
    name: str
    slug: str
    color_hex: str
    type: CategoryType
    total: Decimal
    average: Decimal
    # Status: 'above_average', 'below_average', 'average'
    status: Literal['above_average', 'below_average', 'average']


class MonthlyData(CamelModel):
    month: str
    month_short: str
    year: int
    revenue: Decimal
    expenses: Decimal
    investments: Decimal = Decimal(0)
    balance: Decimal
    categories: List[CategoryMetric]


class DashboardResponse(CamelModel):
    summary: DashboardSummary
    months: List[MonthlyData]

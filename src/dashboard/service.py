from datetime import date, timedelta
from decimal import Decimal
from typing import List, Dict, Tuple, Any
from sqlalchemy.orm import Session
from sqlalchemy import extract, func, select, desc, literal, distinct, and_
from dateutil.relativedelta import relativedelta

from src.entities.payment import Payment
from src.entities.category import Category, CategoryType
from src.dashboard.model import (
    DashboardResponse,
    DashboardSummary,
    DashboardAvailableMonth,
    MonthlyData,
    CategoryMetric,
)

# Local Helpers for Month Names
MONTH_NAMES = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}

MONTH_SHORT = {
    1: "Jan",
    2: "Fev",
    3: "Mar",
    4: "Abr",
    5: "Mai",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Set",
    10: "Out",
    11: "Nov",
    12: "Dez",
}


def get_dashboard_data(
    db: Session, user_id: str, year_mode: str = "last-12"
) -> DashboardResponse:
    """
    Main orchestration function for dashboard data.
    """
    # Pass db and user_id to determine dynamic range based on data
    start_date, end_date = _get_date_range(db, user_id, year_mode)

    # 1. Global Summary (Aggregated in DB)
    summary = _get_global_summary(db, user_id, start_date, end_date)

    # 2. Rolling Averages for Categories (for comparison metrics)
    # Always calculates based on the last 12 months relative to today (or relative to data?)
    # To be consistent, rolling averages should probably align with the view or be strictly recent history.
    # Let's keep rolling averages anchored to "Recent" (Today) for now to represent "current habits",
    # OR match the view window. Matching valid window is safer for historical context.
    # Let's keep it simple and use the same window or standard 12 months.
    # The original code used standard 12 months from today. Let's stick to that for "current norms" unless requested.
    rolling_averages = _get_category_rolling_averages(db, user_id)

    # 3. Monthly Breakdown with Category Data (Aggregated in DB)
    months_data = _get_monthly_breakdown(
        db, user_id, start_date, end_date, rolling_averages
    )

    return DashboardResponse(summary=summary, months=months_data)


def _get_date_range(db: Session, user_id: Any, year_mode: str) -> Tuple[date, date]:
    today = date.today()
    if year_mode == "last-12":
        # Strategy: "Last 12 months WITH DATA"
        # Find the date of the most recent payment
        latest_payment_date = (
            db.query(func.max(Payment.date)).filter(Payment.user_id == user_id).scalar()
        )

        # If we have data, anchor to that. If not, anchor to today.
        anchor_date = latest_payment_date if latest_payment_date else today

        # End date: Last day of the anchor month
        # Start date: First day of the month, 11 months before anchor

        # Example: Anchor = Jan 15 2025.
        # End Window = Jan 31 2025 (or Feb 1 - 1 day)
        # Start Window = Feb 1 2024

        end_date = (anchor_date.replace(day=1) + relativedelta(months=1)) - timedelta(
            days=1
        )
        start_date = end_date.replace(day=1) - relativedelta(months=11)

    else:
        try:
            year = int(year_mode)
            start_date = date(year, 1, 1)
            end_date = date(year, 12, 31)
        except ValueError:
            # Fallback to current year
            start_date = date(today.year, 1, 1)
            end_date = date(today.year, 12, 31)

    return start_date, end_date


def _get_global_summary(
    db: Session, user_id: Any, start_date: date, end_date: date
) -> DashboardSummary:
    """
    Calculates total revenue and expenses entirely in SQL.
    """
    # Join Category to filter by type
    statement = (
        select(Category.type, func.sum(Payment.amount).label("total"))
        .join(Category, Payment.category_id == Category.id)
        .where(
            Payment.user_id == user_id,
            Payment.date >= start_date,
            Payment.date <= end_date,
        )
        .group_by(Category.type)
    )

    results = db.execute(statement).all()

    total_revenue = Decimal(0)
    total_expenses = Decimal(0)

    for category_type, total in results:
        total = (total or Decimal(0)).quantize(Decimal("0.01"))
        if category_type == CategoryType.INCOME:
            total_revenue += total
        elif category_type == CategoryType.EXPENSE:
            total_expenses += total

    return DashboardSummary(
        total_revenue=total_revenue.quantize(Decimal("0.01")),
        total_expenses=total_expenses.quantize(Decimal("0.01")),
        # Expenses are negative, so we ADD them to revenue to get net balance
        balance=(total_revenue + total_expenses).quantize(Decimal("0.01")),
    )


def _get_category_rolling_averages(db: Session, user_id: Any) -> Dict[str, Decimal]:
    """
    Calculates the average monthly spending per category over the last 12 months.
    Formula: Total Spent / 12 (Simple moving average)
    """
    today = date.today()
    start_date = today.replace(day=1) - relativedelta(months=11)

    statement = (
        select(
            Category.slug,
            func.sum(Payment.amount).label("total"),
            func.count(distinct(extract("month", Payment.date))).label("months_count"),
        )
        .join(Category, Payment.category_id == Category.id)
        .where(Payment.user_id == user_id, Payment.date >= start_date)
        .group_by(Category.slug)
    )

    results = db.execute(statement).all()

    # Map category_slug -> average
    # Division by months_count ensures we average against months containing data
    return {
        row.slug: (
            (row.total / row.months_count).quantize(Decimal("0.01"))
            if row.months_count > 0
            else Decimal(0)
        )
        for row in results
    }


def _fill_missing_months(
    start_date: date, end_date: date, existing_data: Dict[Tuple[int, int], Any]
) -> List[MonthlyData]:
    """
    Ensures all months in the range exist in the output, even if empty.
    """
    filled_data = []

    current_date = start_date.replace(day=1)
    while current_date <= end_date:
        key = (current_date.year, current_date.month)

        if key in existing_data:
            filled_data.append(existing_data[key])
        else:
            # Create empty month record
            filled_data.append(
                MonthlyData(
                    month=MONTH_NAMES.get(current_date.month, ""),
                    month_short=MONTH_SHORT.get(current_date.month, ""),
                    year=current_date.year,
                    revenue=Decimal(0),
                    expenses=Decimal(0),
                    balance=Decimal(0),
                    categories=[],
                )
            )

        # Next month
        current_date = current_date + relativedelta(months=1)

    return filled_data


def _get_monthly_breakdown(
    db: Session,
    user_id: Any,
    start_date: date,
    end_date: date,
    averages_map: Dict[str, Decimal],
) -> List[MonthlyData]:
    """
    Fetches monthly data grouped by (Month, Category) via SQL Aggregation.
    """

    # Query: Year, Month, Category Details, Sum(Amount)
    statement = (
        select(
            extract("year", Payment.date).label("year"),
            extract("month", Payment.date).label("month"),
            Category.id.label("category_id"),
            Category.name.label("category_name"),
            Category.slug.label("category_slug"),
            Category.color_hex.label("category_color"),  # Ensure color is fetched
            Category.type.label("category_type"),
            func.sum(Payment.amount).label("total"),
        )
        .join(Category, Payment.category_id == Category.id)
        .where(
            Payment.user_id == user_id,
            Payment.date >= start_date,
            Payment.date <= end_date,
        )
        .group_by(
            extract("year", Payment.date),
            extract("month", Payment.date),
            Category.id,
            Category.name,
            Category.slug,
            Category.color_hex,
            Category.type,
        )
        .order_by(
            extract("year", Payment.date),
            extract("month", Payment.date),
        )
    )

    results = db.execute(statement).all()

    # Process results into nested structure...
    # (Existing map logic)
    monthly_map: Dict[Tuple[int, int], MonthlyData] = {}

    for row in results:
        year = int(row.year)
        month = int(row.month)
        key = (year, month)

        if key not in monthly_map:
            monthly_map[key] = MonthlyData(
                month=MONTH_NAMES.get(month, ""),
                month_short=MONTH_SHORT.get(month, ""),
                year=year,
                revenue=Decimal(0),
                expenses=Decimal(0),
                balance=Decimal(0),
                categories=[],
            )

        amount = (row.total or Decimal(0)).quantize(Decimal("0.01"))

        # Calculate metrics
        average = averages_map.get(row.category_slug, Decimal(0))

        # Use simple magnitude comparison for status
        # This works for both Income (positive) and Expense (negative)
        # "above_average" means "higher magnitude" (more spent OR more earned)
        # "below_average" means "lower magnitude" (less spent OR less earned)

        abs_amount = abs(amount)
        abs_average = abs(average)

        status = "average"
        # Use Decimal for multiplication to avoid TypeError
        if abs_amount > abs_average * Decimal("1.2"):
            status = "above_average"
        elif abs_amount < abs_average * Decimal("0.8"):
            status = "below_average"

        # Add Category Metric
        monthly_map[key].categories.append(
            CategoryMetric(
                name=row.category_name,
                slug=row.category_slug,
                color_hex=row.category_color,
                type=row.category_type,
                total=amount,
                average=average,
                status=status,
            )
        )

        # Update Totals
        if row.category_type == CategoryType.INCOME:
            monthly_map[key].revenue += amount
            monthly_map[key].balance += amount
        elif row.category_type == CategoryType.EXPENSE:
            monthly_map[key].expenses += amount
            # Amount is already negative for expenses, so we ADD it to balance to decrease it.
            monthly_map[key].balance += amount

    # Fill gaps -> NOW REMOVED based on new requirement
    # We just return the sorted map values

    sorted_keys = sorted(monthly_map.keys())
    return [monthly_map[k] for k in sorted_keys]


def get_available_months(db: Session, user_id: Any) -> List[DashboardAvailableMonth]:
    """
    Returns a list of years where the user has payments, plus 'last-12'.
    """
    # Query distinct years from payments
    statement = (
        select(distinct(extract("year", Payment.date)).label("year"))
        .where(Payment.user_id == user_id)
        .order_by(desc("year"))
    )

    results = db.execute(statement).all()

    available_options = [
        DashboardAvailableMonth(label="Últimos 12 meses", value="last-12")
    ]

    for row in results:
        year = int(row.year)
        available_options.append(
            DashboardAvailableMonth(label=str(year), value=str(year), year=year)
        )

    return available_options

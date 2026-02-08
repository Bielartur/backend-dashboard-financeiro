from datetime import date, timedelta
from decimal import Decimal
from typing import List, Dict, Tuple, Any
from sqlalchemy.orm import Session
from sqlalchemy import extract, func, select, desc, literal_column, distinct, and_, text
from sqlalchemy.sql.functions import coalesce
from dateutil.relativedelta import relativedelta

from src.entities.transaction import Transaction, TransactionType
from src.entities.category import Category, UserCategorySetting
from src.dashboard.model import (
    DashboardResponse,
    DashboardSummary,
    DashboardAvailableMonth,
    MonthlyData,
    CategoryMetric,
)
from logging import getLogger

logger = getLogger(__name__)

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

# Categories to exclude from dashboard totals
EXCLUDED_CATEGORY_SLUGS = [
    "transferencia-de-mesma-titularidade",
    "transferencia-mesma-titularidade",
    "transferencia-mesma-instituicao",
    "transferencia-entre-contas",
    "transferência-mesma-titularidade",
    "transferência-mesma-instituição",
    "pagamento-de-cartao-de-credito",
    "pagamento-de-cartão-de-crédito",
]

INVESTMENT_SLUGS = [
    "investimentos",
]


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
        # Find the date of the most recent transaction
        latest_transaction_date = (
            db.query(func.max(Transaction.date))
            .filter(Transaction.user_id == user_id)
            .scalar()
        )

        # If we have data, anchor to that. If not, anchor to today.
        anchor_date = latest_transaction_date if latest_transaction_date else today

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
    Calculates total revenue and expenses, excluding transfers and investments.
    Investments are calculated separately as a net result.
    """
    # Standard Revenue/Expenses (Excluding Investments & Transfers)
    # Group by Payment.type

    statement = (
        select(Transaction.type, func.sum(Transaction.amount).label("total"))
        .join(Category, Transaction.category_id == Category.id)
        .where(
            Transaction.user_id == user_id,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            Category.slug.notin_(EXCLUDED_CATEGORY_SLUGS + INVESTMENT_SLUGS),
        )
        .group_by(Transaction.type)
    )

    results = db.execute(statement).all()

    total_revenue = Decimal(0)
    total_expenses = Decimal(0)

    for payment_type, total in results:
        total = (total or Decimal(0)).quantize(Decimal("0.01"))
        result = (payment_type, total)

        if payment_type == TransactionType.INCOME:
            logger.info(result)
            total_revenue += total
        elif payment_type == TransactionType.EXPENSE:
            logger.info(result)
            total_expenses += total

    # Calculate Net Investment Result
    # Sum of ALL investment transactions (Income + Expense)
    # Income (Redemption) is positive, Expense (Application) is negative.
    inv_statement = (
        select(func.sum(Transaction.amount).label("net_total"))
        .join(Category, Transaction.category_id == Category.id)
        .where(
            Transaction.user_id == user_id,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            Category.slug.in_(INVESTMENT_SLUGS),
        )
    )

    inv_result = db.execute(inv_statement).scalar()
    # User Request:
    # If I redeemed more than I invested (Net positive cash flow), it means I REMOVED money from investments -> Negative Sign.
    # If I invested more than I redeemed (Net negative cash flow), it means I ADDED money to investments -> Positive Sign.
    # So we invert the natural cash flow sign.
    # Natural: Income (Redemption) is +, Expense (Application) is -.
    # Desired: Income is -, Expense is +.
    total_investments = ((inv_result or Decimal(0)) * Decimal("-1")).quantize(
        Decimal("0.01")
    )

    return DashboardSummary(
        total_revenue=total_revenue.quantize(Decimal("0.01")),
        total_expenses=total_expenses.quantize(Decimal("0.01")),
        # Balance = Revenue + Expenses (Expenses are negative)
        balance=(total_revenue + total_expenses).quantize(Decimal("0.01")),
        total_investments=total_investments,
    )


def _get_category_rolling_averages(db: Session, user_id: Any) -> Dict[str, Decimal]:
    """
    Calculates the average monthly spending per category over the last 12 months.
    """
    today = date.today()
    start_date = today.replace(day=1) - relativedelta(months=11)

    statement = (
        select(
            Category.slug.label("category_slug"),
            func.sum(Transaction.amount).label("total"),
            func.count(distinct(extract("month", Transaction.date))).label(
                "months_count"
            ),
        )
        .join(Category, Transaction.category_id == Category.id)
        .where(
            Transaction.user_id == user_id,
            Transaction.date >= start_date,
            Category.slug.notin_(EXCLUDED_CATEGORY_SLUGS),
        )
        .group_by(Category.slug)
    )

    results = db.execute(statement).all()

    return {
        row.category_slug: (
            (row.total / row.months_count).quantize(Decimal("0.01"))
            if row.months_count > 0
            else Decimal(0)
        )
        for row in results
    }


def _get_monthly_breakdown(
    db: Session,
    user_id: Any,
    start_date: date,
    end_date: date,
    averages_map: Dict[str, Decimal],
) -> List[MonthlyData]:
    """
    Fetches monthly data grouped by (Month, Category, Payment Type).
    We group by Payment Type as well to correctly attribute Revenue/Expenses totals,
    then we merge them into the Category line item.
    """

    # Query: Year, Month, Category, Payment Type, Sum(Amount)
    statement = (
        select(
            extract("year", Transaction.date).label("year"),
            extract("month", Transaction.date).label("month"),
            Category.id.label("category_id"),
            coalesce(UserCategorySetting.alias, Category.name).label("category_name"),
            Category.slug.label("category_slug"),
            coalesce(UserCategorySetting.color_hex, Category.color_hex).label(
                "category_color"
            ),
            Transaction.type.label("payment_type"),
            func.sum(Transaction.amount).label("total"),
        )
        .join(Category, Transaction.category_id == Category.id)
        .outerjoin(
            UserCategorySetting,
            and_(
                UserCategorySetting.category_id == Category.id,
                UserCategorySetting.user_id == user_id,
            ),
        )
        .where(
            Transaction.user_id == user_id,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            Category.slug.notin_(EXCLUDED_CATEGORY_SLUGS),
        )
        .group_by(
            extract("year", Transaction.date),
            extract("month", Transaction.date),
            Category.id,
            Category.name,
            Category.slug,
            Category.color_hex,
            UserCategorySetting.alias,
            UserCategorySetting.color_hex,
            Transaction.type,
        )
        .order_by(
            extract("year", Transaction.date),
            extract("month", Transaction.date),
        )
    )

    results = db.execute(statement).all()

    # Process results into nested structure...
    monthly_map: Dict[Tuple[int, int], MonthlyData] = {}

    # Helper to track category metrics indices in the list
    # key: (year, month, slug) -> index in monthly_map[(year, month)].categories
    cat_metric_map: Dict[Tuple[int, int, str], int] = {}

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
                investments=Decimal(0),
                categories=[],
            )

        amount = (row.total or Decimal(0)).quantize(Decimal("0.01"))
        payment_type = row.payment_type
        cat_slug = row.category_slug

        # Check if it's an investment
        is_investment = cat_slug in INVESTMENT_SLUGS

        # Update Monthly Totals
        if is_investment:
            # Add to investments total.
            # Inverting sign as per request: Application (Expense, negative) should increase investment total (positive).
            # Redemption (Income, positive) should decrease investment total (negative).
            monthly_map[key].investments += amount * Decimal("-1")
        else:
            # Regular Revenue/Expenses
            if payment_type == TransactionType.INCOME:
                monthly_map[key].revenue += amount
                monthly_map[key].balance += amount
            elif payment_type == TransactionType.EXPENSE:
                monthly_map[key].expenses += amount
                monthly_map[key].balance += amount

        # Handle Category Metric Merging (We still want to show investments in the category list?)
        # User said "separar ele na parte do dashboard", usually this implies totals.
        # But showing them in the list is fine, they just shouldn't affect the top-level Revenue/Expense cards.

        cat_key = (year, month, cat_slug)

        if cat_key in cat_metric_map:
            # Update existing metric
            idx = cat_metric_map[cat_key]
            metric = monthly_map[key].categories[idx]
            metric.total += amount
            # Recalculate status/type happens partially here or post-loop
        else:
            new_metric = CategoryMetric(
                name=row.category_name,
                slug=row.category_slug,
                color_hex=row.category_color,
                type=payment_type,
                total=amount,
                average=Decimal(0),
                status="average",
            )
            monthly_map[key].categories.append(new_metric)
            cat_metric_map[cat_key] = len(monthly_map[key].categories) - 1

    # Post-process categories to set final Type, Average, Status
    for key, m_data in monthly_map.items():
        for metric in m_data.categories:
            # Set Average
            average = averages_map.get(metric.slug, Decimal(0))
            metric.average = average

            # Set Type based on Net Total
            if metric.total >= 0:
                metric.type = TransactionType.INCOME
            else:
                metric.type = TransactionType.EXPENSE

            # Set Status
            abs_amount = abs(metric.total)
            abs_average = abs(average)

            status = "average"
            if abs_amount > abs_average * Decimal("1.2"):
                status = "above_average"
            elif abs_amount < abs_average * Decimal("0.8"):
                status = "below_average"
            metric.status = status

    sorted_keys = sorted(monthly_map.keys())
    return [monthly_map[k] for k in sorted_keys]


def get_available_months(db: Session, user_id: Any) -> List[DashboardAvailableMonth]:
    """
    Returns a list of years where the user has payments, plus 'last-12'.
    """
    statement = (
        select(distinct(extract("year", Transaction.date)).label("year"))
        .where(Transaction.user_id == user_id)
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

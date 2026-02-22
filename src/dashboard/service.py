from datetime import date, timedelta
from decimal import Decimal
from typing import List, Dict, Tuple, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import (
    extract,
    func,
    select,
    desc,
    literal_column,
    distinct,
    and_,
    or_,
    not_,
    true,
    false,
    text,
    String,
)
from sqlalchemy.sql.functions import coalesce
from dateutil.relativedelta import relativedelta

from src.entities.transaction import Transaction, TransactionType
from src.entities.category import Category, UserCategorySetting
from src.entities.bank import Bank
from src.entities.merchant import Merchant
from src.entities.merchant_alias import MerchantAlias
from src.dashboard.model import (
    DashboardResponse,
    DashboardSummary,
    DashboardAvailableMonth,
    MonthlyData,
    DashboardMetric,
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

# Threshold for grouping small metrics into "Outros" (0.25% = 0.0025)
OTHERS_THRESHOLD = Decimal("0.0025")
OTHERS_INCOME_ID = "__others_income__"
OTHERS_EXPENSE_ID = "__others_expense__"
OTHERS_NAME = "Outros"
OTHERS_COLOR = "#94a3b8"


def _aggregate_small_metrics(
    metrics: List[DashboardMetric], threshold: Decimal = OTHERS_THRESHOLD
) -> List[DashboardMetric]:
    """
    Aggregates metrics that represent <= threshold of the total into a single 'Outros' metric.
    The original metric IDs are preserved in the 'grouped_ids' field.
    'Outros' is always placed at the end of the list.
    """
    if not metrics:
        return metrics

    # Split into Income and Expense
    incomes = [m for m in metrics if m.type == TransactionType.INCOME]
    expenses = [m for m in metrics if m.type == TransactionType.EXPENSE]

    def _process_group(
        group_metrics: List[DashboardMetric], group_type: TransactionType
    ) -> List[DashboardMetric]:
        if not group_metrics:
            return []

        # Calculate total absolute value for this group
        total = sum(abs(m.total) for m in group_metrics)
        if total == 0:
            return group_metrics

        main = []
        others = []

        for m in group_metrics:
            ratio = abs(m.total) / total
            if ratio <= threshold:
                others.append(m)
            else:
                main.append(m)

        if others:
            others_total = sum(m.total for m in others)

            # Determine correct ID based on type
            metric_id = (
                OTHERS_INCOME_ID
                if group_type == TransactionType.INCOME
                else OTHERS_EXPENSE_ID
            )

            others_metric = DashboardMetric(
                id=metric_id,
                name=OTHERS_NAME,
                color_hex=OTHERS_COLOR,
                type=group_type,
                total=others_total,
                average=Decimal(0),
                status="average",
                grouped_ids=[m.id for m in others],
            )
            main.append(others_metric)

        return main

    # Process each group independently
    processed_incomes = _process_group(incomes, TransactionType.INCOME)
    processed_expenses = _process_group(expenses, TransactionType.EXPENSE)

    # Return combined list
    return processed_incomes + processed_expenses


async def get_dashboard_data(
    db: AsyncSession,
    user_id: str,
    year_mode: str = "last-12",
    group_by: str = "category",  # category, merchant, bank
) -> DashboardResponse:
    """
    Main orchestration function for dashboard data.
    """
    # Pass db and user_id to determine dynamic range based on data
    start_date, end_date = await _get_date_range(db, user_id, year_mode)

    # 1. Global Summary (Aggregated in DB)
    summary = await _get_global_summary(db, user_id, start_date, end_date)

    # 2. Rolling Averages for Categories (only if grouping by category)
    rolling_averages = {}
    if group_by == "category":
        rolling_averages = await _get_category_rolling_averages(db, user_id)

    # 3. Monthly Breakdown with Category Data (Aggregated in DB)
    months_data = await _get_monthly_breakdown(
        db, user_id, start_date, end_date, rolling_averages, group_by
    )

    return DashboardResponse(summary=summary, months=months_data)


async def _get_date_range(
    db: AsyncSession, user_id: Any, year_mode: str
) -> Tuple[date, date]:
    today = date.today()
    if year_mode == "last-12":
        # Strategy: "Last 12 months WITH DATA"
        # Find the date of the most recent transaction
        result = await db.execute(
            select(func.max(Transaction.date)).filter(Transaction.user_id == user_id)
        )
        latest_transaction_date = result.scalar()

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


async def _get_global_summary(
    db: AsyncSession, user_id: Any, start_date: date, end_date: date
) -> DashboardSummary:
    """
    Calculates total revenue and expenses, excluding transfers and investments.
    Investments are calculated separately as a net result.
    """
    # Standard Revenue/Expenses (Excluding Investments & Ignored)
    # Group by Payment.type

    # Filter for IGNORED: UserCategorySetting.ignored (prioritized) OR Category.ignored (default) OR MerchantAlias.ignored
    # We want NOT IGNORED.
    # Logic: If user_setting.ignored IS NOT NULL, use it. Else use category.ignored.
    # Also check MerchantAlias.ignored
    category_ignored_check = func.coalesce(
        UserCategorySetting.ignored, Category.ignored
    )
    is_ignored = or_(category_ignored_check.is_(True), MerchantAlias.ignored.is_(True))

    # Filter for INVESTMENT: UserCategorySetting.is_investment (prioritized) OR Category.is_investment (default) OR MerchantAlias.is_investment
    category_investment_check = func.coalesce(
        UserCategorySetting.is_investment, Category.is_investment
    )
    is_investment = or_(
        category_investment_check.is_(True), MerchantAlias.is_investment.is_(True)
    )

    statement = (
        select(Transaction.type, func.sum(Transaction.amount).label("total"))
        .join(Category, Transaction.category_id == Category.id)
        .outerjoin(
            UserCategorySetting,
            and_(
                UserCategorySetting.category_id == Category.id,
                UserCategorySetting.user_id == user_id,
            ),
        )
        .outerjoin(Merchant, Transaction.merchant_id == Merchant.id)
        .outerjoin(MerchantAlias, Merchant.merchant_alias_id == MerchantAlias.id)
        .where(
            Transaction.user_id == user_id,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            # Exclude ignored
            is_ignored.is_(False),
            # Exclude investments (calculated separately)
            is_investment.is_(False),
        )
        .group_by(Transaction.type)
    )

    result = await db.execute(statement)
    results = result.all()

    total_revenue = Decimal(0)
    total_expenses = Decimal(0)

    for payment_type, total in results:
        total = (total or Decimal(0)).quantize(Decimal("0.01"))
        result_tuple = (payment_type, total)

        if payment_type == TransactionType.INCOME:
            logger.info(result_tuple)
            total_revenue += total
        elif payment_type == TransactionType.EXPENSE:
            logger.info(result_tuple)
            total_expenses += total

    # Calculate Net Investment Result
    # Sum of ALL investment transactions (Income + Expense)
    # Income (Redemption) is positive, Expense (Application) is negative.
    inv_statement = (
        select(func.sum(Transaction.amount).label("net_total"))
        .join(Category, Transaction.category_id == Category.id)
        .outerjoin(
            UserCategorySetting,
            and_(
                UserCategorySetting.category_id == Category.id,
                UserCategorySetting.user_id == user_id,
            ),
        )
        .outerjoin(Merchant, Transaction.merchant_id == Merchant.id)
        .outerjoin(MerchantAlias, Merchant.merchant_alias_id == MerchantAlias.id)
        .where(
            Transaction.user_id == user_id,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            is_ignored.is_(False),
            is_investment.is_(True),
        )
    )

    inv_result_exec = await db.execute(inv_statement)
    inv_result = inv_result_exec.scalar()
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


async def _get_category_rolling_averages(
    db: AsyncSession, user_id: Any
) -> Dict[str, Decimal]:
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
            Transaction.date >= start_date,
            func.coalesce(UserCategorySetting.ignored, Category.ignored).is_(False),
        )
        .group_by(Category.slug)
    )

    result = await db.execute(statement)
    results = result.all()

    return {
        row.category_slug: (
            (row.total / row.months_count).quantize(Decimal("0.01"))
            if row.months_count > 0
            else Decimal(0)
        )
        for row in results
    }


async def _get_monthly_breakdown(
    db: AsyncSession,
    user_id: Any,
    start_date: date,
    end_date: date,
    averages_map: Dict[str, Decimal],
    group_by: str = "category",
) -> List[MonthlyData]:
    """
    Fetches monthly data grouped by (Month, Metric, Payment Type).
    Metric can be Category, Merchant, or Bank.
    """

    # 1. Base Query Structure

    # Start with the select columns
    query = select(
        extract("year", Transaction.date).label("year"),
        extract("month", Transaction.date).label("month"),
        Transaction.type.label("payment_type"),
        func.sum(Transaction.amount).label("total"),
        # Add flags for processing
        func.coalesce(UserCategorySetting.is_investment, Category.is_investment).label(
            "cat_is_inv"
        ),
        MerchantAlias.is_investment.label("merch_is_inv"),
    )

    # Apply Joins
    # Hierarchy: Transaction -> Category -> UserCategorySetting
    #                        -> Merchant -> MerchantAlias
    query = (
        query.select_from(Transaction)
        .join(Category, Transaction.category_id == Category.id)
        .outerjoin(
            UserCategorySetting,
            and_(
                UserCategorySetting.category_id == Category.id,
                UserCategorySetting.user_id == user_id,
            ),
        )
        .outerjoin(Merchant, Transaction.merchant_id == Merchant.id)
        .outerjoin(MerchantAlias, Merchant.merchant_alias_id == MerchantAlias.id)
    )

    # Filter
    query = query.where(
        Transaction.user_id == user_id,
        Transaction.date >= start_date,
        Transaction.date <= end_date,
        # Exclude Ignored
        or_(
            func.coalesce(UserCategorySetting.ignored, Category.ignored).is_(True),
            MerchantAlias.ignored.is_(True),
        ).is_(False),
    )

    # 2. Add Grouping Specifics
    if group_by == "category":
        # JOINs are already done above. We just need to add columns and group by.
        query = query.add_columns(
            Category.id.label("metric_id"),
            func.coalesce(UserCategorySetting.alias, Category.name).label(
                "metric_name"
            ),
            Category.slug.label("metric_slug_or_id"),
            func.coalesce(UserCategorySetting.color_hex, Category.color_hex).label(
                "metric_color"
            ),
            literal_column("'black'").label("metric_icon"),  # Placeholder
        ).group_by(
            Category.id,
            Category.name,
            Category.slug,
            Category.color_hex,
            UserCategorySetting.alias,
            UserCategorySetting.color_hex,
        )

    elif group_by == "merchant":
        # JOIN Merchant -> MerchantAlias (Already joined)
        query = query.add_columns(
            MerchantAlias.id.label("metric_id"),
            MerchantAlias.pattern.label("metric_name"),
            func.cast(MerchantAlias.id, String).label("metric_slug_or_id"),
            literal_column("'#64748b'").label("metric_color"),  # Default color for now
            literal_column("NULL").label("metric_icon"),
        ).group_by(
            MerchantAlias.id,
            MerchantAlias.pattern,
        )

    elif group_by == "bank":
        # JOIN Bank
        query = (
            query.add_columns(
                Bank.id.label("metric_id"),
                Bank.name.label("metric_name"),
                Bank.slug.label("metric_slug_or_id"),
                Bank.color_hex.label("metric_color"),
                Bank.logo_url.label("metric_icon"),
            )
            .join(Bank, Transaction.bank_id == Bank.id)
            .group_by(Bank.id, Bank.name, Bank.slug, Bank.color_hex, Bank.logo_url)
        )

    # Add common group by (Year, Month, Type) and Order
    # Also group by flags since we selected them
    query = query.group_by(
        extract("year", Transaction.date),
        extract("month", Transaction.date),
        Transaction.type,
        func.coalesce(UserCategorySetting.is_investment, Category.is_investment),
        MerchantAlias.is_investment,
    ).order_by(
        extract("year", Transaction.date),
        extract("month", Transaction.date),
    )

    result = await db.execute(query)
    results = result.all()

    # Process results
    monthly_map: Dict[Tuple[int, int], MonthlyData] = {}
    metric_map: Dict[Tuple[int, int, str], int] = (
        {}
    )  # (year, month, metric_id) -> index

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
                metrics=[],
            )

        amount = (row.total or Decimal(0)).quantize(Decimal("0.01"))
        payment_type = row.payment_type

        # Identifier for the metric (slug for categories, uuid for others)
        metric_identifier = str(row.metric_slug_or_id)

        # Check if it's an investment
        is_investment = row.cat_is_inv or row.merch_is_inv

        if is_investment:
            monthly_map[key].investments += amount * Decimal("-1")
        else:
            if payment_type == TransactionType.INCOME:
                monthly_map[key].revenue += amount
                monthly_map[key].balance += amount
            elif payment_type == TransactionType.EXPENSE:
                monthly_map[key].expenses += amount
                monthly_map[key].balance += amount

        # Add/Update Metric
        metric_key = (year, month, metric_identifier)

        if metric_key in metric_map:
            idx = metric_map[metric_key]
            metric = monthly_map[key].metrics[idx]
            metric.total += amount
        else:
            # Color Generation for Merchant if needed
            color = row.metric_color
            if group_by == "merchant":
                # Simple hash for consistent color
                # In a real app, we might want a stored color or a better algorithm
                import hashlib

                hash_object = hashlib.md5(row.metric_name.encode())
                hex_dig = hash_object.hexdigest()
                color = f"#{hex_dig[:6]}"

            new_metric = DashboardMetric(
                id=metric_identifier,
                name=row.metric_name,
                color_hex=color,
                logo_url=str(row.metric_icon) if row.metric_icon else None,
                type=payment_type,
                total=amount,
                average=Decimal(0),
                status="unknown",
            )
            monthly_map[key].metrics.append(new_metric)
            metric_map[metric_key] = len(monthly_map[key].metrics) - 1

    # Post-process (Averages, Status)
    for key, m_data in monthly_map.items():
        for metric in m_data.metrics:
            # Calculate Status only for Categories for now
            if group_by == "category":
                average = averages_map.get(metric.id, Decimal(0))
                metric.average = average

                # Set Type based on Net Total
                if metric.total >= 0:
                    metric.type = TransactionType.INCOME
                else:
                    metric.type = TransactionType.EXPENSE

                abs_amount = abs(metric.total)
                abs_average = abs(average)

                status = "average"
                if abs_average > 0:
                    if abs_amount > abs_average * Decimal("1.2"):
                        status = "above_average"
                    elif abs_amount < abs_average * Decimal("0.8"):
                        status = "below_average"

                metric.status = status
            else:
                # For Banks/Merchants, decide default status
                metric.status = "average"
                if metric.total >= 0:
                    metric.type = TransactionType.INCOME
                else:
                    metric.type = TransactionType.EXPENSE

    sorted_keys = sorted(monthly_map.keys())

    # Aggregate small metrics into "Outros" for merchant grouping only
    if group_by == "merchant":
        for key in sorted_keys:
            monthly_map[key].metrics = _aggregate_small_metrics(
                monthly_map[key].metrics
            )

    return [monthly_map[k] for k in sorted_keys]


async def get_available_months(
    db: AsyncSession, user_id: Any
) -> List[DashboardAvailableMonth]:
    """
    Returns a list of years where the user has payments, plus 'last-12'.
    """
    statement = (
        select(distinct(extract("year", Transaction.date)).label("year"))
        .where(Transaction.user_id == user_id)
        .order_by(desc("year"))
    )

    result = await db.execute(statement)
    results = result.all()

    available_options = [
        DashboardAvailableMonth(label="Últimos 12 meses", value="last-12")
    ]

    for row in results:
        year = int(row.year)
        available_options.append(
            DashboardAvailableMonth(label=str(year), value=str(year), year=year)
        )

    return available_options

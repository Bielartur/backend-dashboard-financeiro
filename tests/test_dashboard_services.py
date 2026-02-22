import pytest
from decimal import Decimal
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from sqlalchemy.ext.asyncio import AsyncSession

from src.dashboard import service
from src.dashboard.model import DashboardMetric
from src.entities.transaction import TransactionType
from src.dashboard.service import (
    OTHERS_INCOME_ID,
    OTHERS_EXPENSE_ID,
    OTHERS_NAME,
    OTHERS_COLOR,
    MONTH_NAMES,
)

# --- Tests for _aggregate_small_metrics ---


def test_aggregate_small_metrics_empty():
    assert service._aggregate_small_metrics([]) == []


def test_aggregate_small_metrics_no_grouping_needed():
    metrics = [
        DashboardMetric(
            id="1",
            name="A",
            color_hex="#000",
            type=TransactionType.EXPENSE,
            total=Decimal("-100"),
        ),
        DashboardMetric(
            id="2",
            name="B",
            color_hex="#000",
            type=TransactionType.EXPENSE,
            total=Decimal("-100"),
        ),
    ]
    # Total = 200. Threshold 0.25% is 0.5. Both are 100 (50%). No grouping.
    result = service._aggregate_small_metrics(metrics)
    assert len(result) == 2
    assert result[0].id == "1"
    assert result[1].id == "2"


def test_aggregate_small_metrics_grouping():
    # Total = 1000. Threshold 0.25% = 2.5
    metrics = [
        DashboardMetric(
            id="A",
            name="A",
            color_hex="#0",
            type=TransactionType.EXPENSE,
            total=Decimal("-990"),
        ),
        DashboardMetric(
            id="B",
            name="B",
            color_hex="#0",
            type=TransactionType.EXPENSE,
            total=Decimal("-1"),
        ),
        DashboardMetric(
            id="C",
            name="C",
            color_hex="#0",
            type=TransactionType.EXPENSE,
            total=Decimal("-1"),
        ),
        DashboardMetric(
            id="D",
            name="D",
            color_hex="#0",
            type=TransactionType.EXPENSE,
            total=Decimal("-8"),
        ),
    ]

    result = service._aggregate_small_metrics(metrics, threshold=Decimal("0.0025"))

    # Expected: A, D, Outros
    assert len(result) == 3
    ids = [m.id for m in result]
    assert "A" in ids
    assert "D" in ids
    assert OTHERS_EXPENSE_ID in ids

    others = next(m for m in result if m.id == OTHERS_EXPENSE_ID)
    assert others.name == OTHERS_NAME
    assert others.color_hex == OTHERS_COLOR
    assert others.total == Decimal("-2")
    assert others.grouped_ids == ["B", "C"]


def test_aggregate_small_metrics_mixed_signs():
    metrics = [
        DashboardMetric(
            id="IncA",
            name="Inc A",
            color_hex="#0",
            type=TransactionType.INCOME,
            total=Decimal("1000"),
        ),
        DashboardMetric(
            id="IncB",
            name="Inc B",
            color_hex="#0",
            type=TransactionType.INCOME,
            total=Decimal("5"),
        ),
        DashboardMetric(
            id="ExpA",
            name="Exp A",
            color_hex="#0",
            type=TransactionType.EXPENSE,
            total=Decimal("-500"),
        ),
        DashboardMetric(
            id="ExpB",
            name="Exp B",
            color_hex="#0",
            type=TransactionType.EXPENSE,
            total=Decimal("-2"),
        ),
    ]
    # Total Volume = 1507. 1% = 15.07.
    # IncB (5) and ExpB (2) are both small.

    result = service._aggregate_small_metrics(metrics, threshold=Decimal("0.01"))

    # Expect: IncA, ExpA, Outros(Income), Outros(Expense)
    assert len(result) == 4

    ids = [m.id for m in result]
    assert "IncA" in ids
    assert "ExpA" in ids

    # Check for Outros
    # Check for IDs
    ids = [m.id for m in result]
    assert OTHERS_INCOME_ID in ids
    assert OTHERS_EXPENSE_ID in ids

    outros_inc = next(m for m in result if m.id == OTHERS_INCOME_ID)
    assert outros_inc.total == Decimal("5")
    assert outros_inc.grouped_ids == ["IncB"]

    outros_exp = next(m for m in result if m.id == OTHERS_EXPENSE_ID)
    assert outros_exp.total == Decimal("-2")
    assert outros_exp.grouped_ids == ["ExpB"]


# --- Tests for _get_date_range ---


@pytest.mark.asyncio
async def test_get_date_range_specific_year(db_session, test_user):
    year_mode = "2023"
    start, end = await service._get_date_range(db_session, test_user.id, year_mode)
    assert start == date(2023, 1, 1)
    assert end == date(2023, 12, 31)


@pytest.mark.asyncio
async def test_get_date_range_invalid_year_fallback(db_session, test_user):
    today = date.today()
    start, end = await service._get_date_range(db_session, test_user.id, "invalid")
    assert start == date(today.year, 1, 1)
    assert end == date(today.year, 12, 31)


@pytest.mark.asyncio
async def test_get_date_range_last12_no_data(db_session, test_user):
    today = date.today()
    expected_end = (today.replace(day=1) + relativedelta(months=1)) - timedelta(days=1)
    expected_start = expected_end.replace(day=1) - relativedelta(months=11)

    start, end = await service._get_date_range(db_session, test_user.id, "last-12")
    assert start == expected_start
    assert end == expected_end


@pytest.mark.asyncio
async def test_get_date_range_last12_with_data(
    db_session, test_user, transaction_factory
):
    # Anchor: 2 months ago
    today = date.today()
    tx_date = today - relativedelta(months=2)

    await transaction_factory(date=tx_date)

    start, end = await service._get_date_range(db_session, test_user.id, "last-12")

    expected_end = (tx_date.replace(day=1) + relativedelta(months=1)) - timedelta(
        days=1
    )
    expected_start = expected_end.replace(day=1) - relativedelta(months=11)

    assert start == expected_start
    assert end == expected_end


# --- Tests for get_available_months ---


@pytest.mark.asyncio
async def test_get_available_months(db_session, test_user, transaction_factory):
    # Insert transactions in different years
    await transaction_factory(date=date(2022, 5, 1))
    await transaction_factory(date=date(2023, 1, 1))

    options = await service.get_available_months(db_session, test_user.id)

    # Expect "last-12", "2023", "2022"
    assert len(options) == 3
    assert options[0].value == "last-12"

    years = [o.year for o in options if o.year]
    assert 2023 in years
    assert 2022 in years


# --- Tests for get_dashboard_data ---


@pytest.mark.asyncio
async def test_get_dashboard_data_empty(db_session, test_user):
    data = await service.get_dashboard_data(db_session, test_user.id, "last-12")

    assert data.summary.total_revenue == Decimal("0.00")
    assert data.summary.total_expenses == Decimal("0.00")
    assert data.summary.balance == Decimal("0.00")
    assert data.summary.total_investments == Decimal("0.00")
    assert len(data.months) == 0


@pytest.mark.asyncio
async def test_get_dashboard_data_basic_flow(
    db_session, test_user, transaction_factory, sample_category
):
    # Add income and expense
    today = date.today()

    # Income
    await transaction_factory(
        amount=Decimal("1000.50"),
        date=today,
        type=TransactionType.INCOME,
    )

    # Expense
    await transaction_factory(
        amount=Decimal("-500.25"),
        date=today,
        type=TransactionType.EXPENSE,
    )

    data = await service.get_dashboard_data(db_session, test_user.id, "last-12")

    # Summary
    assert data.summary.total_revenue == Decimal("1000.50")
    assert data.summary.total_expenses == Decimal("-500.25")
    assert data.summary.balance == Decimal("500.25")

    # Check Monthly Breakdown
    assert len(data.months) >= 1
    m_data = data.months[-1]  # Latest
    assert m_data.revenue == Decimal("1000.50")
    assert m_data.expenses == Decimal("-500.25")
    assert m_data.balance == Decimal("500.25")

    # Check metrics
    assert len(m_data.metrics) == 1
    metric = m_data.metrics[0]
    assert metric.id == str(sample_category.slug)
    assert metric.total == Decimal("500.25")  # Net 1000.50 - 500.25
    assert metric.type == TransactionType.INCOME


@pytest.mark.asyncio
async def test_get_dashboard_data_exclusions(
    db_session, test_user, sample_category, transaction_factory
):
    # 1. Ignored Category
    # 2. Ignored Merchant Alias

    from src.entities.category import UserCategorySetting, Category
    from src.entities.merchant import Merchant
    from src.entities.merchant_alias import MerchantAlias

    # Ignored User Setting
    setting = UserCategorySetting(
        user_id=test_user.id,
        category_id=sample_category.id,
        ignored=True,
        color_hex="#000000",
    )
    db_session.add(setting)
    await db_session.commit()

    # Ignored Merchant Alias
    alias_ignored = MerchantAlias(user_id=test_user.id, pattern="Ignored", ignored=True)
    db_session.add(alias_ignored)
    await db_session.commit()
    await db_session.refresh(alias_ignored)

    merchant_ignored = Merchant(
        name="Ignored Store", merchant_alias_id=alias_ignored.id, user_id=test_user.id
    )
    db_session.add(merchant_ignored)
    await db_session.commit()
    await db_session.refresh(merchant_ignored)

    # Valid Category for Merchant test
    cat2 = Category(name="Valid Cat", slug="valid-cat", color_hex="#fff")
    db_session.add(cat2)
    await db_session.commit()
    await db_session.refresh(cat2)

    # TX 1: Ignored Category
    await transaction_factory(
        category_id=sample_category.id,
        amount=Decimal("-100"),
    )

    # TX 2: Ignored Merchant (but valid category)
    await transaction_factory(
        category_id=cat2.id,
        merchant_id=merchant_ignored.id,
        amount=Decimal("-50"),
    )

    data = await service.get_dashboard_data(db_session, test_user.id, "last-12")

    # Both excluded
    assert data.summary.total_expenses == Decimal("0.00")


@pytest.mark.asyncio
async def test_get_dashboard_data_investments(
    db_session, test_user, sample_category, transaction_factory
):
    from src.entities.category import UserCategorySetting

    # Mark category as investment
    setting = UserCategorySetting(
        user_id=test_user.id,
        category_id=sample_category.id,
        is_investment=True,
        color_hex="#000000",
    )
    db_session.add(setting)
    await db_session.commit()

    # Application (Expense)
    await transaction_factory(
        category_id=sample_category.id,
        amount=Decimal("-1000"),
        type=TransactionType.EXPENSE,
    )

    # Redemption (Income)
    await transaction_factory(
        category_id=sample_category.id,
        amount=Decimal("200"),
        type=TransactionType.INCOME,
    )

    data = await service.get_dashboard_data(db_session, test_user.id, "last-12")

    # Excluded from Revenue/Expense
    assert data.summary.total_revenue == Decimal("0.00")
    assert data.summary.total_expenses == Decimal("0.00")

    # Investment Total: -1 * (-1000 + 200) = 800
    assert data.summary.total_investments == Decimal("800.00")


@pytest.mark.asyncio
async def test_get_dashboard_data_grouping(
    db_session,
    test_user,
    sample_transaction,
    sample_category,
    sample_merchant,
    sample_bank,
):
    # sample_transaction already has all fields set

    # 1. Group by Category
    data_cat = await service.get_dashboard_data(
        db_session, test_user.id, "last-12", group_by="category"
    )
    m_cat = data_cat.months[-1].metrics[0]
    assert m_cat.name == sample_category.name

    # 2. Group by Merchant
    data_merch = await service.get_dashboard_data(
        db_session, test_user.id, "last-12", group_by="merchant"
    )
    m_merch = data_merch.months[-1].metrics[0]
    # Merchant Name comes from Alias Name usually, but logic in service:
    # MerchantAlias.pattern.label("metric_name")
    # Sample merchant alias name/pattern should be checked.
    # sample_merchant fixture creates "Uber".
    assert "Uber" in m_merch.name or "Uber" == m_merch.name

    # 3. Group by Bank
    data_bank = await service.get_dashboard_data(
        db_session, test_user.id, "last-12", group_by="bank"
    )
    m_bank = data_bank.months[-1].metrics[0]
    assert m_bank.name == sample_bank.name


@pytest.mark.asyncio
async def test_category_rolling_average_status(
    db_session, test_user, transaction_factory
):
    today = date.today()
    month_ago = today - relativedelta(months=1)

    # Past
    await transaction_factory(
        amount=Decimal("-100"), date=month_ago, type=TransactionType.EXPENSE
    )

    # Current (Above Average)
    await transaction_factory(
        amount=Decimal("-200"), date=today, type=TransactionType.EXPENSE
    )

    data = await service.get_dashboard_data(
        db_session, test_user.id, "last-12", group_by="category"
    )

    # Find month matching today.month and today.year
    m_data = next(
        m for m in data.months if m.year == today.year and m.month == "Fevereiro"
    )  # Assuming Feb for test but need dynamic match
    # Better: use month index if available in model or check month_short/month name against helper
    # MonthlyData has year and month (string name) and month_short.
    # But wait, MONTH_NAMES[today.month] gives the name.

    from src.dashboard.service import MONTH_NAMES

    current_month_name = MONTH_NAMES[today.month]

    m_data = next(
        m for m in data.months if m.year == today.year and m.month == current_month_name
    )
    metric = m_data.metrics[0]

    # Avg -150
    assert metric.average == Decimal("-150.00")
    assert metric.status == "above_average"

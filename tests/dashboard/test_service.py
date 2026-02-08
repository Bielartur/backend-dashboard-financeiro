import pytest
from decimal import Decimal
from datetime import date
from unittest.mock import MagicMock
from src.dashboard.service import _get_monthly_breakdown
from src.dashboard.model import MonthlyData, CategoryMetric
from src.entities.transaction import TransactionType


# Mock Row object from sqlalchemy result
class MockRow:
    def __init__(
        self,
        year,
        month,
        category_id,
        category_name,
        category_slug,
        category_color,
        payment_type,
        total,
    ):
        self.year = year
        self.month = month
        self.category_id = category_id
        self.category_name = category_name
        self.category_slug = category_slug
        self.category_color = category_color
        self.payment_type = payment_type
        self.total = total


def test_spending_status_logic():
    # Setup
    start_date = date(2023, 1, 1)
    end_date = date(2023, 1, 31)
    user_id = "test-user"

    # Averages Map:
    # Expense: -100 (avg)
    # Income: 100 (avg)
    averages_map = {"expense-avg": Decimal("-100.00"), "income-avg": Decimal("100.00")}

    # Mock DB Results
    # 1. Expense - Below Average (Magnitude < 80) -> -50
    # 2. Expense - Average ( 80 <= Magnitude <= 120 ) -> -100
    # 3. Expense - Above Average (Magnitude > 120) -> -150

    # 4. Income - Below Average (Magnitude < 80) -> 50
    # 5. Income - Average -> 100
    # 6. Income - Above Average -> 150

    mock_results = [
        MockRow(
            2023,
            1,
            "id1",
            "Exp Below",
            "expense-below",
            "#000",
            TransactionType.EXPENSE,
            Decimal("-50.00"),
        ),
        MockRow(
            2023,
            1,
            "id2",
            "Exp Avg",
            "expense-avg",
            "#000",
            TransactionType.EXPENSE,
            Decimal("-100.00"),
        ),
        MockRow(
            2023,
            1,
            "id3",
            "Exp Above",
            "expense-above",
            "#000",
            TransactionType.EXPENSE,
            Decimal("-150.00"),
        ),
        MockRow(
            2023,
            1,
            "id4",
            "Inc Below",
            "income-below",
            "#000",
            TransactionType.INCOME,
            Decimal("50.00"),
        ),
        MockRow(
            2023,
            1,
            "id5",
            "Inc Avg",
            "income-avg",
            "#000",
            TransactionType.INCOME,
            Decimal("100.00"),
        ),
        MockRow(
            2023,
            1,
            "id6",
            "Inc Above",
            "income-above",
            "#000",
            TransactionType.INCOME,
            Decimal("150.00"),
        ),
    ]

    # Update averages map to match slugs of test cases for simplicity (reuse avg 100 for all)
    averages_map = {
        "expense-below": Decimal("-100.00"),
        "expense-avg": Decimal("-100.00"),
        "expense-above": Decimal("-100.00"),
        "income-below": Decimal("100.00"),
        "income-avg": Decimal("100.00"),
        "income-above": Decimal("100.00"),
    }

    mock_db_session = MagicMock()
    mock_db_session.execute.return_value.all.return_value = mock_results

    # Execute
    result = _get_monthly_breakdown(
        mock_db_session, user_id, start_date, end_date, averages_map
    )

    assert len(result) == 1
    month_data = result[0]
    cats = {c.slug: c for c in month_data.categories}

    # Verify Expenses
    # -50 vs -100 avg -> Magnitude 50 vs 100 -> 0.5 ratio -> < 0.8 -> below_average
    assert cats["expense-below"].status == "below_average"

    # -100 vs -100 avg -> Magnitude 100 vs 100 -> 1.0 ratio -> average
    assert cats["expense-avg"].status == "average"

    # -150 vs -100 avg -> Magnitude 150 vs 100 -> 1.5 ratio -> > 1.2 -> above_average
    assert cats["expense-above"].status == "above_average"

    # Verify Income
    # 50 vs 100 avg -> below_average
    assert cats["income-below"].status == "below_average"

    # 100 vs 100 avg -> average
    assert cats["income-avg"].status == "average"

    # 150 vs 100 avg -> above_average
    assert cats["income-above"].status == "above_average"

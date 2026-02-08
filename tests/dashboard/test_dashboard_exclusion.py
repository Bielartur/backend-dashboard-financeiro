from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from src.dashboard.service import get_dashboard_data
from src.entities.category import Category
from src.entities.transaction import Transaction, TransactionMethod, TransactionType
from src.entities.bank import Bank
from src.entities.user import User


def test_dashboard_excludes_credit_card_payments(db_session: Session):
    # 1. Setup User
    user_id = uuid4()
    user = User(
        id=user_id,
        email="test@example.com",
        first_name="Test",
        last_name="User",
        password_hash="pw",
    )
    db_session.add(user)
    db_session.flush()

    # 2. Setup Category "Pagamento de Cartão de Crédito"
    # Ensure slug matches exactly what we expect to exclude
    cc_category = Category(
        id=uuid4(),
        name="Pagamento de Cartão de Crédito",
        slug="pagamento-de-cartao-de-credito",
        user_id=None,  # System category
        parent_id=None,  # Root
        color_hex="#000000",
    )
    db_session.add(cc_category)

    # 3. Setup Variant Category "Pagamento de Cartão" (Name match check)
    cc_category_variant = Category(
        id=uuid4(),
        name="Pagamento de Cartão",
        slug="pagamento-de-cartao",
        user_id=user_id,
        parent_id=None,
        color_hex="#000000",
    )
    db_session.add(cc_category_variant)

    # 3.5 Setup Bank
    bank = Bank(
        id=uuid4(),
        name="Test Bank",
        slug="test-bank",
        color_hex="#000000",
        logo_url="http://test.com/logo.png",
    )
    db_session.add(bank)

    # 4. Create Payments
    today = date.today()

    # Payment 1: Income assigned to CC Category (Should be EXCLUDED)
    p1 = Transaction(
        id=uuid4(),
        user_id=user_id,
        title="Payment received",
        amount=Decimal("1000.00"),
        date=today,
        type=TransactionType.INCOME,
        category_id=cc_category.id,
        payment_method=TransactionMethod.CreditCard,
        bank_id=bank.id,
    )

    # Payment 2: Income assigned to Variant Category (Should be EXCLUDED)
    p2 = Transaction(
        id=uuid4(),
        user_id=user_id,
        title="Payment received variant",
        amount=Decimal("500.00"),
        date=today,
        type=TransactionType.INCOME,
        category_id=cc_category_variant.id,
        payment_method=TransactionMethod.CreditCard,
        bank_id=bank.id,
    )

    # Payment 3: Valid Income (Should be INCLUDED)
    salary_category = Category(
        id=uuid4(),
        name="Salário",
        slug="salario",
        user_id=user_id,
        parent_id=None,  # Root
        color_hex="#00FF00",
    )
    db_session.add(salary_category)

    p3 = Transaction(
        id=uuid4(),
        user_id=user_id,
        title="Salary",
        amount=Decimal("5000.00"),
        date=today,
        type=TransactionType.INCOME,
        category_id=salary_category.id,
        payment_method=TransactionMethod.Pix,
        bank_id=bank.id,
    )

    db_session.add_all([p1, p2, p3])
    db_session.commit()

    # 5. Run Dashboard Service
    data = get_dashboard_data(db_session, user_id, "last-12")

    # 6. Verify Summary
    # Total Revenue should ONLY be 5000.00 (Salary).
    # If 1000 or 500 are included, it fails.

    print(f"Total Revenue: {data.summary.total_revenue}")
    print(f"Total Expenses: {data.summary.total_expenses}")

    assert data.summary.total_revenue == Decimal("5000.00")

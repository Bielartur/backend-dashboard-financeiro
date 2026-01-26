import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import date
from decimal import Decimal
from uuid import uuid4
from src.payments import service, model
from src.payments.model import (
    PaymentCreate,
    PaymentUpdate,
    PaymentMethod,
    ImportType,
    ImportSource,
    PaymentImportResponse,
)
from src.entities.payment import Payment
from src.entities.category import Category, CategoryType
from src.entities.merchant import Merchant
from src.entities.merchant_alias import MerchantAlias
from src.entities.bank import Bank
from src.exceptions.payments import (
    PaymentNotFoundError,
    PaymentCreationError,
    PaymentImportError,
)
from fastapi import UploadFile


@pytest.fixture
def sample_category(db_session):
    category = Category(
        name="Test Category",
        slug="test-category",
        color_hex="#000000",
        type=CategoryType.EXPENSE,
    )
    db_session.add(category)
    db_session.commit()
    db_session.refresh(category)
    return category


@pytest.fixture
def income_category(db_session):
    category = Category(
        name="Income Category",
        slug="income-category",
        color_hex="#00FF00",
        type=CategoryType.INCOME,
    )
    db_session.add(category)
    db_session.commit()
    db_session.refresh(category)
    return category


@pytest.fixture
def expense_category(db_session):
    category = Category(
        name="Expense Category",
        slug="expense-category",
        color_hex="#FF0000",
        type=CategoryType.EXPENSE,
    )
    db_session.add(category)
    db_session.commit()
    db_session.refresh(category)
    return category


@pytest.fixture
def sample_merchant(db_session, test_user, sample_category):
    alias = MerchantAlias(user_id=test_user.id, pattern="Test Merchant")
    db_session.add(alias)
    db_session.flush()

    merchant = Merchant(
        name="Test Merchant",
        user_id=test_user.id,
        category_id=sample_category.id,
        merchant_alias_id=alias.id,
    )
    db_session.add(merchant)
    db_session.commit()
    db_session.refresh(merchant)
    return merchant


def test_create_payment(
    db_session, token_data, test_user, sample_category, sample_bank
):
    payment_data = PaymentCreate(
        title="Test Payment",
        date=date(2023, 10, 1),
        amount=Decimal("-50.00"),
        payment_method=PaymentMethod.CreditCard,
        bank_id=sample_bank.id,
        category_id=sample_category.id,
    )
    payment = service.create_payment(token_data, db_session, payment_data)
    assert payment.id is not None
    assert payment.title == "Test Payment"


def test_get_payment_by_id(
    db_session, token_data, test_user, sample_category, sample_merchant, sample_bank
):
    payment = Payment(
        user_id=test_user.id,
        category_id=sample_category.id,
        merchant_id=sample_merchant.id,
        title="Manual Payment",
        date=date(2023, 10, 1),
        amount=Decimal("-10.00"),
        bank_id=sample_bank.id,
    )
    db_session.add(payment)
    db_session.commit()
    fetched = service.get_payment_by_id(token_data, db_session, payment.id)
    assert fetched.title == "Manual Payment"


def test_get_payment_not_found(db_session, token_data, test_user):
    with pytest.raises(PaymentNotFoundError):
        service.get_payment_by_id(token_data, db_session, uuid4())


def test_update_payment(
    db_session, token_data, test_user, sample_category, sample_merchant, sample_bank
):
    payment = Payment(
        user_id=test_user.id,
        category_id=sample_category.id,
        merchant_id=sample_merchant.id,
        title="Old Title",
        date=date(2023, 10, 1),
        amount=Decimal("-10.00"),
        bank_id=sample_bank.id,
    )
    db_session.add(payment)
    db_session.commit()
    update_data = PaymentUpdate(title="New Title", amount=Decimal("-20.00"))
    updated = service.update_payment(token_data, db_session, payment.id, update_data)
    assert updated.title == "New Title"


def test_delete_payment(
    db_session, token_data, test_user, sample_category, sample_merchant, sample_bank
):
    payment = Payment(
        user_id=test_user.id,
        category_id=sample_category.id,
        merchant_id=sample_merchant.id,
        title="To Delete",
        date=date(2023, 10, 1),
        amount=Decimal("-10.00"),
        bank_id=sample_bank.id,
    )
    db_session.add(payment)
    db_session.commit()
    service.delete_payment(token_data, db_session, payment.id)
    with pytest.raises(PaymentNotFoundError):
        service.get_payment_by_id(token_data, db_session, payment.id)


def test_search_payments(
    db_session, token_data, test_user, sample_category, sample_merchant, sample_bank
):
    p1 = Payment(
        user_id=test_user.id,
        category_id=sample_category.id,
        merchant_id=sample_merchant.id,
        title="Alpha",
        date=date(2023, 10, 1),
        amount=Decimal("-10"),
        bank_id=sample_bank.id,
    )
    p2 = Payment(
        user_id=test_user.id,
        category_id=sample_category.id,
        merchant_id=sample_merchant.id,
        title="Beta",
        date=date(2023, 10, 2),
        amount=Decimal("-20"),
        bank_id=sample_bank.id,
    )
    p3 = Payment(
        user_id=test_user.id,
        category_id=sample_category.id,
        merchant_id=sample_merchant.id,
        title="Gamma",
        date=date(2023, 10, 3),
        amount=Decimal("-30"),
        bank_id=sample_bank.id,
    )
    db_session.add_all([p1, p2, p3])
    db_session.commit()
    result = service.search_payments(token_data, db_session, query="Alpha")
    assert result.total == 1
    result = service.search_payments(
        token_data, db_session, query="", start_date=date(2023, 10, 2)
    )
    assert result.total == 2


# --- Bulk Create Tests ---


def test_bulk_create_payment_success(
    db_session, token_data, test_user, sample_category, sample_bank, sample_merchant
):
    payments_data = [
        PaymentCreate(
            title="Bulk 1",
            date=date(2023, 10, 1),
            amount=Decimal("-10.00"),
            payment_method=PaymentMethod.CreditCard,
            merchant_id=sample_merchant.id,
            bank_id=sample_bank.id,
            category_id=sample_category.id,
        ),
        PaymentCreate(
            title="Bulk 2",
            date=date(2023, 10, 2),
            amount=Decimal("-20.00"),
            payment_method=PaymentMethod.DebitCard,
            merchant_id=sample_merchant.id,
            bank_id=sample_bank.id,
            category_id=sample_category.id,
        ),
    ]
    created = service.bulk_create_payment(token_data, db_session, payments_data)
    assert len(created) == 2
    assert created[0].title == "Bulk 1"
    assert created[1].title == "Bulk 2"


def test_bulk_create_payment_idempotency(
    db_session, token_data, test_user, sample_category, sample_bank
):
    pid1 = uuid4()
    p1 = PaymentCreate(
        id=pid1,
        title="Unique Payment",
        date=date(2023, 10, 1),
        amount=Decimal("-10.00"),
        payment_method=PaymentMethod.CreditCard,
        bank_id=sample_bank.id,
        category_id=sample_category.id,
    )

    # First creation
    created_first = service.bulk_create_payment(token_data, db_session, [p1])
    assert len(created_first) == 1

    # Second creation (same ID) -> Should be ignored
    created_second = service.bulk_create_payment(token_data, db_session, [p1])
    # The return behavior depends on DB support for RETURNING on conflict.
    # In many setups, conflict returns nothing.
    assert len(created_second) == 0

    count = db_session.query(Payment).count()
    assert count == 1


# --- Import Deduplication Tests ---


@pytest.mark.asyncio
async def test_import_deduplication_invoice_signature(
    db_session, token_data, test_user, sample_bank, sample_category, sample_merchant
):
    # Existing payment
    existing = Payment(
        user_id=test_user.id,
        category_id=sample_category.id,
        title="Netflix",
        date=date(2023, 10, 1),
        amount=Decimal("-50.00"),
        bank_id=sample_bank.id,
        payment_method=PaymentMethod.CreditCard,
        merchant_id=sample_merchant.id,
    )
    db_session.add(existing)
    db_session.commit()

    # Simulate parser output with one DUPLICATE and one NEW
    duplicate = PaymentImportResponse(
        date=date(2023, 10, 1),
        title="Netflix",
        amount=Decimal("-50.00"),
        payment_method="credit_card",
        has_merchant=True,
    )
    new_tx = PaymentImportResponse(
        date=date(2023, 10, 2),
        title="Spotify",
        amount=Decimal("-30.00"),
        payment_method="credit_card",
        has_merchant=True,
    )

    mock_parser = MagicMock()
    mock_parser.parse_invoice = AsyncMock(return_value=[duplicate, new_tx])

    with patch("src.payments.service.get_parser", return_value=mock_parser):
        # Using CREDIT_CARD_INVOICE triggers signature check
        result = await service.import_payments_from_csv(
            token_data,
            db_session,
            MagicMock(spec=UploadFile),
            ImportSource.NUBANK,
            ImportType.CREDIT_CARD_INVOICE,
        )

        # Duplicate should be marked
        assert len(result) == 2
        # Sort order: No Category (0) -> Category (1). Our mocks don't have category set by parser, but logic sets it.
        # Let's find by title
        res_dup = next(r for r in result if r.title == "Netflix")
        res_new = next(r for r in result if r.title == "Spotify")

        assert res_dup.already_exists is True
        assert res_new.already_exists is False


@pytest.mark.asyncio
async def test_import_deduplication_statement_id(
    db_session, token_data, test_user, sample_bank, sample_category, sample_merchant
):
    # Existing payment WITH ID
    pid = uuid4()
    existing = Payment(
        id=pid,
        user_id=test_user.id,
        category_id=sample_category.id,
        merchant_id=sample_merchant.id,
        title="Transfer",
        date=date(2023, 10, 1),
        amount=Decimal("-100.00"),
        bank_id=sample_bank.id,
        payment_method=PaymentMethod.Pix,
    )
    db_session.add(existing)
    db_session.commit()

    # Simulate parser output with ID
    duplicate = PaymentImportResponse(
        id=pid,
        date=date(2023, 10, 1),
        title="Transfer",
        amount=Decimal("-100.00"),
        payment_method="pix",
    )

    mock_parser = MagicMock()
    mock_parser.parse_statement = AsyncMock(return_value=[duplicate])

    with patch("src.payments.service.get_parser", return_value=mock_parser):
        # Using BANK_STATEMENT triggers ID check
        result = await service.import_payments_from_csv(
            token_data,
            db_session,
            MagicMock(spec=UploadFile),
            ImportSource.NUBANK,
            ImportType.BANK_STATEMENT,
        )

        assert len(result) == 1
        assert result[0].already_exists is True


# --- Category Validation Tests ---


def test_category_validation_mismatch_expense_with_income_category(
    db_session, token_data, income_category, sample_bank
):
    # Attempt to create Expense (-50) with Income Category
    payment_data = PaymentCreate(
        title="Invalid Expense",
        date=date(2023, 10, 1),
        amount=Decimal("-50.00"),
        payment_method=PaymentMethod.CreditCard,
        bank_id=sample_bank.id,
        category_id=income_category.id,
    )

    # Expecting failure as per requirements
    with pytest.raises(PaymentCreationError) as exc:
        service.create_payment(token_data, db_session, payment_data)

    assert (
        "não pode ter categoria de" in str(exc.value).lower()
        or "mismatch" in str(exc.value).lower()
    )


def test_category_validation_mismatch_income_with_expense_category(
    db_session, token_data, expense_category, sample_bank
):
    # Attempt to create Income (+50) with Expense Category
    payment_data = PaymentCreate(
        title="Invalid Income",
        date=date(2023, 10, 1),
        amount=Decimal("50.00"),
        payment_method=PaymentMethod.CreditCard,
        bank_id=sample_bank.id,
        category_id=expense_category.id,
    )

    with pytest.raises(PaymentCreationError) as exc:
        service.create_payment(token_data, db_session, payment_data)

import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import date
from decimal import Decimal
from uuid import uuid4
from src.transactions import service, model
from src.transactions.model import (
    TransactionCreate,
    TransactionUpdate,
    TransactionImportResponse,
    ImportType,
    ImportSource,
)
from src.entities.transaction import Transaction, TransactionMethod
from src.entities.category import Category
from src.entities.merchant import Merchant
from src.entities.merchant_alias import MerchantAlias
from src.entities.bank import Bank
from src.exceptions.transactions import (
    TransactionNotFoundError,
    TransactionCreationError,
    TransactionImportError,
)
from fastapi import UploadFile


@pytest.fixture
def sample_category(db_session):
    category = Category(
        name="Test Category",
        slug="test-category",
        color_hex="#000000",
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


def test_create_transaction(
    db_session, token_data, test_user, sample_category, sample_bank
):
    transaction_data = TransactionCreate(
        title="Test Transaction",
        date=date(2023, 10, 1),
        amount=Decimal("-50.00"),
        payment_method=PaymentMethod.CreditCard,
        bank_id=sample_bank.id,
        category_id=sample_category.id,
    )
    transaction = service.create_transaction(token_data, db_session, transaction_data)
    assert transaction.id is not None
    assert transaction.title == "Test Transaction"


def test_get_transaction_by_id(
    db_session, token_data, test_user, sample_category, sample_merchant, sample_bank
):
    transaction = Transaction(
        user_id=test_user.id,
        category_id=sample_category.id,
        merchant_id=sample_merchant.id,
        title="Manual Transaction",
        date=date(2023, 10, 1),
        amount=Decimal("-10.00"),
        bank_id=sample_bank.id,
    )
    db_session.add(transaction)
    db_session.commit()
    fetched = service.get_transaction_by_id(token_data, db_session, transaction.id)
    assert fetched.title == "Manual Transaction"


def test_get_transaction_not_found(db_session, token_data, test_user):
    with pytest.raises(TransactionNotFoundError):
        service.get_transaction_by_id(token_data, db_session, uuid4())


def test_update_transaction(
    db_session, token_data, test_user, sample_category, sample_merchant, sample_bank
):
    transaction = Transaction(
        user_id=test_user.id,
        category_id=sample_category.id,
        merchant_id=sample_merchant.id,
        title="Old Title",
        date=date(2023, 10, 1),
        amount=Decimal("-10.00"),
        bank_id=sample_bank.id,
    )
    db_session.add(transaction)
    db_session.commit()
    update_data = TransactionUpdate(title="New Title", amount=Decimal("-20.00"))
    updated = service.update_transaction(
        token_data, db_session, transaction.id, update_data
    )
    assert updated.title == "New Title"


def test_delete_transaction(
    db_session, token_data, test_user, sample_category, sample_merchant, sample_bank
):
    transaction = Transaction(
        user_id=test_user.id,
        category_id=sample_category.id,
        merchant_id=sample_merchant.id,
        title="To Delete",
        date=date(2023, 10, 1),
        amount=Decimal("-10.00"),
        bank_id=sample_bank.id,
    )
    db_session.add(transaction)
    db_session.commit()
    service.delete_transaction(token_data, db_session, transaction.id)
    with pytest.raises(TransactionNotFoundError):
        service.get_transaction_by_id(token_data, db_session, transaction.id)


def test_search_transactions(
    db_session, token_data, test_user, sample_category, sample_merchant, sample_bank
):
    t1 = Transaction(
        user_id=test_user.id,
        category_id=sample_category.id,
        merchant_id=sample_merchant.id,
        title="Alpha",
        date=date(2023, 10, 1),
        amount=Decimal("-10"),
        bank_id=sample_bank.id,
    )
    t2 = Transaction(
        user_id=test_user.id,
        category_id=sample_category.id,
        merchant_id=sample_merchant.id,
        title="Beta",
        date=date(2023, 10, 2),
        amount=Decimal("-20"),
        bank_id=sample_bank.id,
    )
    t3 = Transaction(
        user_id=test_user.id,
        category_id=sample_category.id,
        merchant_id=sample_merchant.id,
        title="Gamma",
        date=date(2023, 10, 3),
        amount=Decimal("-30"),
        bank_id=sample_bank.id,
    )
    db_session.add_all([t1, t2, t3])
    db_session.commit()
    result = service.search_transactions(token_data, db_session, query="Alpha")
    assert result.total == 1
    result = service.search_transactions(
        token_data, db_session, query="", start_date=date(2023, 10, 2)
    )
    assert result.total == 2


# --- Bulk Create Tests ---


def test_bulk_create_transaction_success(
    db_session, token_data, test_user, sample_category, sample_bank, sample_merchant
):
    transactions_data = [
        TransactionCreate(
            title="Bulk 1",
            date=date(2023, 10, 1),
            amount=Decimal("-10.00"),
            payment_method=PaymentMethod.CreditCard,
            merchant_id=sample_merchant.id,
            bank_id=sample_bank.id,
            category_id=sample_category.id,
        ),
        TransactionCreate(
            title="Bulk 2",
            date=date(2023, 10, 2),
            amount=Decimal("-20.00"),
            payment_method=PaymentMethod.DebitCard,
            merchant_id=sample_merchant.id,
            bank_id=sample_bank.id,
            category_id=sample_category.id,
        ),
    ]
    created = service.bulk_create_transaction(token_data, db_session, transactions_data)
    assert len(created) == 2
    assert created[0].title == "Bulk 1"
    assert created[1].title == "Bulk 2"


def test_bulk_create_transaction_idempotency(
    db_session, token_data, test_user, sample_category, sample_bank
):
    pid1 = uuid4()
    p1 = TransactionCreate(
        id=pid1,
        title="Unique Transaction",
        date=date(2023, 10, 1),
        amount=Decimal("-10.00"),
        payment_method=PaymentMethod.CreditCard,
        bank_id=sample_bank.id,
        category_id=sample_category.id,
    )

    # First creation
    created_first = service.bulk_create_transaction(token_data, db_session, [p1])
    assert len(created_first) == 1

    # Second creation (same ID) -> Should be ignored
    created_second = service.bulk_create_transaction(token_data, db_session, [p1])
    # The return behavior depends on DB support for RETURNING on conflict.
    # In many setups, conflict returns nothing.
    assert len(created_second) == 0

    count = db_session.query(Transaction).count()
    assert count == 1


# --- Import Deduplication Tests ---


@pytest.mark.asyncio
async def test_import_deduplication_invoice_signature(
    db_session, token_data, test_user, sample_bank, sample_category, sample_merchant
):
    # Existing transaction
    existing = Transaction(
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
    duplicate = TransactionImportResponse(
        date=date(2023, 10, 1),
        title="Netflix",
        amount=Decimal("-50.00"),
        payment_method="credit_card",
        has_merchant=True,
    )
    new_tx = TransactionImportResponse(
        date=date(2023, 10, 2),
        title="Spotify",
        amount=Decimal("-30.00"),
        payment_method="credit_card",
        has_merchant=True,
    )

    mock_parser = MagicMock()
    mock_parser.parse_invoice = AsyncMock(return_value=[duplicate, new_tx])

    with patch("src.transactions.service.get_parser", return_value=mock_parser):
        # Using CREDIT_CARD_INVOICE triggers signature check
        result = await service.import_transactions_from_csv(
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
    # Existing transaction WITH ID
    pid = uuid4()
    existing = Transaction(
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
    duplicate = TransactionImportResponse(
        id=pid,
        date=date(2023, 10, 1),
        title="Transfer",
        amount=Decimal("-100.00"),
        payment_method="pix",
    )

    mock_parser = MagicMock()
    mock_parser.parse_statement = AsyncMock(return_value=[duplicate])

    with patch("src.transactions.service.get_parser", return_value=mock_parser):
        # Using BANK_STATEMENT triggers ID check
        result = await service.import_transactions_from_csv(
            token_data,
            db_session,
            MagicMock(spec=UploadFile),
            ImportSource.NUBANK,
            ImportType.BANK_STATEMENT,
        )

        assert len(result) == 1
        assert result[0].already_exists is True

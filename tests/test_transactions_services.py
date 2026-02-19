import pytest
import uuid
from datetime import date, timedelta
from decimal import Decimal
from src.transactions import service, model
from src.entities.transaction import TransactionType, TransactionMethod
from src.exceptions.transactions import (
    TransactionNotFoundError,
    TransactionCreationError,
)


@pytest.mark.asyncio
async def test_create_transaction_success(
    db_session, token_data, sample_category, sample_bank
):
    payload = model.TransactionCreate(
        title="Service Transaction",
        amount=Decimal("-50.00"),
        date=date.today(),
        payment_method=TransactionMethod.Pix,
        bank_id=sample_bank.id,
        category_id=sample_category.id,
    )
    transaction = await service.create_transaction(token_data, db_session, payload)
    assert transaction.title == "Service Transaction"
    assert transaction.amount == Decimal("-50.00")
    assert transaction.type == TransactionType.EXPENSE


@pytest.mark.asyncio
async def test_get_transaction_by_id_success(
    db_session, token_data, sample_bank, sample_category
):
    # Create first
    payload = model.TransactionCreate(
        title="To Fetch",
        amount=Decimal("-10.00"),
        date=date.today(),
        payment_method=TransactionMethod.Pix,
        bank_id=sample_bank.id,
        category_id=sample_category.id,
    )
    created = await service.create_transaction(token_data, db_session, payload)

    fetched = await service.get_transaction_by_id(token_data, db_session, created.id)
    assert fetched.id == created.id
    assert fetched.title == "To Fetch"


@pytest.mark.asyncio
async def test_get_transaction_by_id_not_found(db_session, token_data):
    with pytest.raises(TransactionNotFoundError):
        await service.get_transaction_by_id(token_data, db_session, uuid.uuid4())


@pytest.mark.asyncio
async def test_update_transaction_success(
    db_session, token_data, sample_bank, sample_category
):
    # Create
    payload = model.TransactionCreate(
        title="To Update",
        amount=Decimal("-10.00"),
        date=date.today(),
        payment_method=TransactionMethod.Pix,
        bank_id=sample_bank.id,
        category_id=sample_category.id,
    )
    created = await service.create_transaction(token_data, db_session, payload)

    # Update
    update_data = model.TransactionUpdate(
        title="Updated Title", amount=Decimal("-20.00")
    )
    updated = await service.update_transaction(
        token_data, db_session, created.id, update_data
    )

    assert updated.title == "Updated Title"
    assert updated.amount == Decimal("-20.00")


@pytest.mark.asyncio
async def test_delete_transaction_success(
    db_session, token_data, sample_bank, sample_category
):
    # Create
    payload = model.TransactionCreate(
        title="To Delete",
        amount=Decimal("-10.00"),
        date=date.today(),
        payment_method=TransactionMethod.Pix,
        bank_id=sample_bank.id,
        category_id=sample_category.id,
    )
    created = await service.create_transaction(token_data, db_session, payload)

    # Delete
    await service.delete_transaction(token_data, db_session, created.id)

    # Verify
    with pytest.raises(TransactionNotFoundError):
        await service.get_transaction_by_id(token_data, db_session, created.id)


@pytest.mark.asyncio
async def test_search_transactions_filters(
    db_session, token_data, sample_bank, sample_category
):
    # Create mixed transactions
    # 1. Expense today
    t1 = await service.create_transaction(
        token_data,
        db_session,
        model.TransactionCreate(
            title="Lunch",
            amount=Decimal("-20.00"),
            date=date.today(),
            payment_method=TransactionMethod.DebitCard,
            bank_id=sample_bank.id,
            category_id=sample_category.id,
        ),
    )
    # 2. Income yesterday
    t2 = await service.create_transaction(
        token_data,
        db_session,
        model.TransactionCreate(
            title="Salary",
            amount=Decimal("1000.00"),
            date=date.today() - timedelta(days=1),
            payment_method=TransactionMethod.Pix,
            bank_id=sample_bank.id,
            category_id=sample_category.id,
        ),
    )

    # Filter by query
    res = await service.search_transactions(token_data, db_session, query="Lunch")
    assert len(res.items) == 1
    assert res.items[0].id == t1.id

    # Filter by type
    res = await service.search_transactions(
        token_data,
        db_session,
        query="",
        type=TransactionType.INCOME,
    )
    assert len(res.items) == 1
    assert res.items[0].id == t2.id

    # Filter by date range
    res = await service.search_transactions(
        token_data,
        db_session,
        query="",
        start_date=date.today(),
    )
    assert len(res.items) == 1
    assert res.items[0].id == t1.id


@pytest.mark.asyncio
async def test_bulk_create_transaction(
    db_session, token_data, sample_category, sample_bank
):
    payloads = [
        model.TransactionCreate(
            title="Bulk 1",
            amount=Decimal("-10.00"),
            date=date.today(),
            category_id=sample_category.id,
            bank_id=sample_bank.id,
        ),
        model.TransactionCreate(
            title="Bulk 2",
            amount=Decimal("-20.00"),
            date=date.today(),
            category_id=sample_category.id,
            bank_id=sample_bank.id,
        ),
    ]

    created = await service.bulk_create_transaction(token_data, db_session, payloads)
    assert len(created) == 2
    assert created[0].title == "Bulk 1"
    assert created[1].title == "Bulk 2"


@pytest.mark.asyncio
async def test_update_transactions_category_bulk(
    db_session, token_data, sample_bank, sample_category
):
    from src.entities.category import Category

    # Create a target category to update TO
    target_category = Category(
        id=uuid.uuid4(),
        name="Target Category",
        slug="target-category",
        color_hex="#0000FF",
    )
    db_session.add(target_category)
    await db_session.commit()
    await db_session.refresh(target_category)

    # Create transactions with sample_category initially
    t1 = await service.create_transaction(
        token_data,
        db_session,
        model.TransactionCreate(
            title="Bulk Update 1",
            amount=Decimal("-10.00"),
            date=date.today(),
            payment_method=TransactionMethod.Pix,
            bank_id=sample_bank.id,
            category_id=sample_category.id,
            has_merchant=True,
        ),
    )

    # Create another one for same merchant (same title)
    t2 = await service.create_transaction(
        token_data,
        db_session,
        model.TransactionCreate(
            title="Bulk Update 1",  # Same title -> Same merchant
            amount=Decimal("-20.00"),
            date=date.today(),
            payment_method=TransactionMethod.Pix,
            bank_id=sample_bank.id,
            category_id=sample_category.id,
            has_merchant=True,
        ),
    )

    assert t1.merchant_id is not None
    assert t1.merchant_id == t2.merchant_id

    # Perform bulk update to target_category
    count = await service.update_transactions_category_bulk(
        db_session,
        token_data.get_uuid(),  # Service expects UUID
        [t1.merchant_id],
        target_category.id,
    )

    assert count == 2

    # Verify updates
    await db_session.refresh(t1)
    await db_session.refresh(t2)
    assert t1.category_id == target_category.id
    assert t2.category_id == target_category.id


@pytest.mark.asyncio
async def test_import_transactions_invoice_success(db_session, token_data, sample_bank):
    from unittest.mock import MagicMock, patch
    from fastapi import UploadFile
    from src.transactions.model import (
        ImportSource,
        ImportType,
        TransactionImportResponse,
    )

    # Mock file with filename indicating invoice
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "invoice.csv"

    # Data provided by user for Invoice
    # 2026-01-31,Caradegato,23.00
    # 2026-01-31,Dl*99 Ride,4.32
    # ...
    # Note: Invoice parsers usually return positive amounts for expenses (cost),
    # but the service might expect them signed?
    # Looking at service logic (line 610): `is_negative = transaction.amount < 0`.
    # If the parser returns positive for expense, the service treats it as income unless parser handles sign.
    # Standard parsers (Nubank) often return positive for expense.
    # However, TransactionImportResponse expects the *final* amount usually?
    # Let's assume the PARSER does the sign conversion.
    # Nubank invoice items are expenses, so should be negative in TransactionImportResponse.

    mock_parsed_txs = [
        TransactionImportResponse(
            date=date(2026, 1, 31),
            title="Caradegato",
            amount=Decimal("-23.00"),
            has_merchant=True,
        ),
        TransactionImportResponse(
            date=date(2026, 1, 31),
            title="Dl*99 Ride",
            amount=Decimal("-4.32"),
            has_merchant=True,
        ),
        TransactionImportResponse(
            date=date(2026, 1, 31),
            title="Pg *Medprev - Parcela 1/2",
            amount=Decimal("-55.00"),
            has_merchant=True,
        ),
        TransactionImportResponse(
            date=date(2026, 1, 31),
            title="Dl*99 Ride",
            amount=Decimal("-6.80"),
            has_merchant=True,
        ),
        TransactionImportResponse(
            date=date(2026, 1, 31),
            title="Supermercado Novo Hori",
            amount=Decimal("-5.49"),
            has_merchant=True,
        ),
        TransactionImportResponse(
            date=date(2026, 1, 30),
            title="Mp *Hiracai",
            amount=Decimal("-24.00"),
            has_merchant=True,
        ),
        TransactionImportResponse(
            date=date(2026, 1, 30),
            title="Pg *99 Ride",
            amount=Decimal("-4.16"),
            has_merchant=True,
        ),
        TransactionImportResponse(
            date=date(2026, 1, 29),
            title="Morada Recife Delicate",
            amount=Decimal("-12.50"),
            has_merchant=True,
        ),
        TransactionImportResponse(
            date=date(2026, 1, 28),
            title="Dl*99 Ride",
            amount=Decimal("-7.90"),
            has_merchant=True,
        ),
    ]

    # Mock Parser
    mock_parser = MagicMock()
    mock_parser.parse_invoice = MagicMock(return_value=mock_parsed_txs)

    with patch("src.transactions.service.get_parser", return_value=mock_parser):
        results = await service.import_transactions_from_csv(
            token_data,
            db_session,
            mock_file,
            ImportSource.NUBANK,
            ImportType.CREDIT_CARD_INVOICE,
        )

        assert len(results) == 9
        assert results[0].title == "Caradegato"
        assert results[0].amount == Decimal("-23.00")
        assert results[-1].title == "Dl*99 Ride"
        mock_parser.parse_invoice.assert_called_once()


@pytest.mark.asyncio
async def test_import_transactions_statement_success(
    db_session, token_data, sample_bank
):
    from unittest.mock import MagicMock, patch
    from fastapi import UploadFile
    from src.transactions.model import (
        ImportSource,
        ImportType,
        TransactionImportResponse,
    )

    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "statement.csv"

    # Data provided by user for Statement
    # 01/01/2026,-5.00,...
    mock_parsed_txs = [
        TransactionImportResponse(
            date=date(2026, 1, 1),
            title="Transferência enviada pelo Pix - Mariana do Carmo...",
            amount=Decimal("-5.00"),
            has_merchant=True,
        ),
        TransactionImportResponse(
            date=date(2026, 1, 1),
            title="Transferência enviada pelo Pix - Edmilson Pedro...",
            amount=Decimal("-10.00"),
            has_merchant=True,
        ),
        TransactionImportResponse(
            date=date(2026, 1, 1),
            title="Transferência enviada pelo Pix - Gilnaldo José...",
            amount=Decimal("-5.00"),
            has_merchant=True,
        ),
        TransactionImportResponse(
            date=date(2026, 1, 1),
            title="Transferência enviada pelo Pix - SEVERINO BATISTA...",
            amount=Decimal("-9.00"),
            has_merchant=True,
        ),
        TransactionImportResponse(
            date=date(2026, 1, 1),
            title="Transferência enviada pelo Pix - SEVERINO BATISTA...",
            amount=Decimal("-2.00"),
            has_merchant=True,
        ),
        TransactionImportResponse(
            date=date(2026, 1, 2),
            title="Transferência enviada pelo Pix - MARIA BETANIA...",
            amount=Decimal("-5.00"),
            has_merchant=True,
        ),
        TransactionImportResponse(
            date=date(2026, 1, 3),
            title="Transferência enviada pelo Pix - PAGAR.ME PAGAME...",
            amount=Decimal("-569.55"),
            has_merchant=True,
        ),
        TransactionImportResponse(
            date=date(2026, 1, 4),
            title="Compra de criptomoedas",
            amount=Decimal("-400.00"),
            has_merchant=True,
        ),
        TransactionImportResponse(
            date=date(2026, 1, 4),
            title="Compra no débito - ATACAREJO BONGI",
            amount=Decimal("-5.98"),
            has_merchant=True,
        ),
        TransactionImportResponse(
            date=date(2026, 1, 4),
            title="Transferência enviada pelo Pix - SHPP BRASIL...",
            amount=Decimal("-19.00"),
            has_merchant=True,
        ),
        TransactionImportResponse(
            date=date(2026, 1, 5),
            title="Transferência enviada pelo Pix - MARIA BETANIA...",
            amount=Decimal("-167.50"),
            has_merchant=True,
        ),
        TransactionImportResponse(
            date=date(2026, 1, 5),
            title="Transferência recebida pelo Pix - Maria Betania...",
            amount=Decimal("210.00"),
            has_merchant=True,
        ),
    ]

    mock_parser = MagicMock()
    mock_parser.parse_statement = MagicMock(return_value=mock_parsed_txs)

    with patch("src.transactions.service.get_parser", return_value=mock_parser):
        results = await service.import_transactions_from_csv(
            token_data,
            db_session,
            mock_file,
            ImportSource.NUBANK,
            ImportType.BANK_STATEMENT,
        )

        assert len(results) == 12
        assert results[0].amount == Decimal("-5.00")
        assert results[-1].amount == Decimal("210.00")
        mock_parser.parse_statement.assert_called_once()

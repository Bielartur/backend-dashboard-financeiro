import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch

from fastapi import UploadFile
from src.transactions import service
from src.transactions.model import ImportSource, ImportType, TransactionImportResponse
from src.exceptions.transactions import TransactionImportError


@pytest.mark.asyncio
async def test_import_transactions_invoice_success(db_session, token_data, sample_bank):
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "invoice.csv"

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

    mock_parser = MagicMock()
    mock_parser.parse_invoice = AsyncMock(return_value=mock_parsed_txs)

    with patch(
        "src.transactions.service.import_service.get_parser", return_value=mock_parser
    ):
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
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "statement.csv"

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
    mock_parser.parse_statement = AsyncMock(return_value=mock_parsed_txs)

    with patch(
        "src.transactions.service.import_service.get_parser", return_value=mock_parser
    ):
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


@pytest.mark.asyncio
async def test_import_transactions_unknown_type(db_session, token_data):
    mock_file = AsyncMock(spec=UploadFile)

    with pytest.raises(TransactionImportError) as exc_info:
        await service.import_transactions_from_csv(
            token_data,
            db_session,
            mock_file,
            ImportSource.NUBANK,
            "INVALID_TYPE",
        )

    assert "Tipo de importação desconhecido" in str(exc_info.value)


@pytest.mark.asyncio
async def test_import_transactions_unsupported_bank(db_session, token_data):
    mock_file = AsyncMock(spec=UploadFile)
    mock_parsed_txs = [
        TransactionImportResponse(
            date=date(2026, 1, 1),
            title="Test",
            amount=Decimal("-5.00"),
            has_merchant=True,
        )
    ]

    mock_parser = MagicMock()
    mock_parser.parse_statement = AsyncMock(return_value=mock_parsed_txs)

    with patch(
        "src.transactions.service.import_service.get_parser", return_value=mock_parser
    ):
        with pytest.raises(TransactionImportError) as exc_info:
            await service.import_transactions_from_csv(
                token_data,
                db_session,
                mock_file,
                ImportSource.ITAU,
                ImportType.BANK_STATEMENT,
            )

        assert "O banco 'itau' ainda não é suportado pelo sistema" in str(
            exc_info.value
        )


@pytest.mark.asyncio
async def test_import_transactions_parser_error(db_session, token_data):
    mock_file = AsyncMock(spec=UploadFile)

    mock_parser = MagicMock()
    mock_parser.parse_statement = AsyncMock(side_effect=Exception("Parser crashed!"))

    with patch(
        "src.transactions.service.import_service.get_parser", return_value=mock_parser
    ):
        with pytest.raises(TransactionImportError) as exc_info:
            await service.import_transactions_from_csv(
                token_data,
                db_session,
                mock_file,
                ImportSource.NUBANK,
                ImportType.BANK_STATEMENT,
            )

        assert (
            "Ocorreu um erro inesperado durante a importação: Parser crashed!"
            in str(exc_info.value)
        )


@pytest.mark.asyncio
async def test_import_transactions_with_merchant_category(
    db_session, token_data, sample_bank, sample_category, sample_merchant
):
    sample_merchant.category_id = sample_category.id
    db_session.add(sample_merchant)
    await db_session.commit()

    mock_file = AsyncMock(spec=UploadFile)
    mock_parsed_txs = [
        TransactionImportResponse(
            date=date(2026, 1, 1),
            title=sample_merchant.name,
            amount=Decimal("-15.00"),
            has_merchant=True,
        )
    ]
    mock_parser = MagicMock()
    mock_parser.parse_statement = AsyncMock(return_value=mock_parsed_txs)

    with patch(
        "src.transactions.service.import_service.get_parser", return_value=mock_parser
    ):
        results = await service.import_transactions_from_csv(
            token_data,
            db_session,
            mock_file,
            ImportSource.NUBANK,
            ImportType.BANK_STATEMENT,
        )

    assert len(results) == 1
    assert results[0].title == sample_merchant.name
    assert results[0].category is not None
    assert results[0].category.id == sample_category.id
    assert results[0].category.name == sample_category.name


@pytest.mark.asyncio
async def test_get_import_transaction_range_empty():
    min_date, max_date = await service.import_service._get_import_transaction_range([])
    assert min_date is None
    assert max_date is None


def test_is_duplicate_transaction_credit_card():
    tx = TransactionImportResponse(
        date=date(2026, 1, 1), title="Uber", amount=Decimal("-10.00")
    )

    existing_signatures = {(date(2026, 1, 1), Decimal("-10.00"), "Uber")}
    assert (
        service.import_service._is_duplicate_transaction(
            tx, ImportType.CREDIT_CARD_INVOICE, set(), existing_signatures
        )
        is True
    )

    existing_signatures_diff = {(date(2026, 1, 1), Decimal("-12.00"), "Uber")}
    assert (
        service.import_service._is_duplicate_transaction(
            tx, ImportType.CREDIT_CARD_INVOICE, set(), existing_signatures_diff
        )
        is False
    )

    assert (
        service.import_service._is_duplicate_transaction(
            tx, "SOME_UNKNOWN_TYPE", set(), set()
        )
        is False
    )


@pytest.mark.asyncio
async def test_import_transactions_empty_file(db_session, token_data):
    mock_file = AsyncMock(spec=UploadFile)
    mock_parser = MagicMock()
    mock_parser.parse_statement = AsyncMock(return_value=[])

    with patch(
        "src.transactions.service.import_service.get_parser", return_value=mock_parser
    ):
        results = await service.import_transactions_from_csv(
            token_data,
            db_session,
            mock_file,
            ImportSource.NUBANK,
            ImportType.BANK_STATEMENT,
        )
        assert results == []

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import UploadFile
from datetime import date
from decimal import Decimal
from src.payments.parsers.nubank import NubankParser
from src.entities.payment import PaymentMethod


@pytest.fixture
def nubank_parser():
    return NubankParser()


@pytest.mark.asyncio
async def test_parse_invoice_valid_csv(nubank_parser):
    # Mock content: date,title,amount
    csv_content = """date,title,amount
2023-10-01,Lunch,25.50
2023-10-02,Uber,15.00
2023-10-03,Pagamento recebido,-100.00
"""
    mock_file = MagicMock(spec=UploadFile)
    mock_file.read = AsyncMock(return_value=csv_content.encode("utf-8"))

    results = await nubank_parser.parse_invoice(mock_file)

    assert len(results) == 3

    # Check Expense (Positive in CSV -> Negative Amount)
    assert results[0].date == date(2023, 10, 1)
    assert results[0].title == "Lunch"
    assert results[0].amount == Decimal("-25.50")
    assert results[0].payment_method.value == PaymentMethod.CreditCard.value

    # Check Payment (Negative in CSV -> Positive Amount) "Pagamento recebido"
    assert results[2].date == date(2023, 10, 3)
    assert results[2].title == "Pagamento recebido"
    assert results[2].amount == Decimal("100.00")
    assert results[2].payment_method.value == PaymentMethod.BillPayment.value


@pytest.mark.asyncio
async def test_parse_statement_valid_csv(nubank_parser):
    # Mock content: Data,Valor,Identificador,Descrição
    csv_content = """Data,Valor,Identificador,Descrição
01/10/2023,-50.00,uuid-1234,Transferência enviada pelo Pix - João Silva
02/10/2023,-20.00,uuid-5678,Compra no débito - Padaria
03/10/2023,-100.00,uuid-9012,Pagamento de fatura
04/10/2023,1000.00,uuid-3456,Transferência recebida pelo Pix - Salary
"""
    mock_file = MagicMock(spec=UploadFile)
    mock_file.read = AsyncMock(return_value=csv_content.encode("utf-8"))

    results = await nubank_parser.parse_statement(mock_file)

    assert len(results) == 4

    # Pix Sent
    assert results[0].payment_method.value == PaymentMethod.Pix.value
    assert results[0].amount == Decimal("-50.00")
    assert "João Silva" in results[0].title

    # Debit Purchase
    assert results[1].payment_method.value == PaymentMethod.DebitCard.value
    assert results[1].amount == Decimal("-20.00")
    assert "Padaria" in results[1].title

    # Bill Payment
    assert results[2].payment_method.value == PaymentMethod.BillPayment.value
    assert results[2].amount == Decimal("-100.00")

    # Pix Received
    assert results[3].payment_method.value == PaymentMethod.Pix.value
    assert results[3].amount == Decimal("1000.00")

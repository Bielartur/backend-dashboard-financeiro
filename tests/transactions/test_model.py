import pytest
from uuid import uuid4
from decimal import Decimal
from datetime import date, datetime
from src.transactions.model import (
    TransactionResponse,
    TransactionImportResponse,
    TransactionMethodSchema,
)
from src.entities.transaction import TransactionMethod
from src.categories.model import CategoryResponse


def test_transaction_response_convert_payment_method_enum():
    """Test converting TransactionMethod Enum to Schema in TransactionResponse"""
    category_data = CategoryResponse(
        id=uuid4(),
        name="Test Cat",
        slug="test-cat",
        color_hex="#000000",
        is_active=True,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    response = TransactionResponse(
        id=uuid4(),
        user_id=uuid4(),
        title="Test",
        date=date(2023, 10, 1),
        amount=Decimal("100.00"),
        bank_id=uuid4(),
        category=category_data,
        payment_method=TransactionMethod.CreditCard,
        has_merchant=True,
    )

    assert isinstance(response.payment_method, TransactionMethodSchema)
    assert response.payment_method.value == "credit_card"
    assert response.payment_method.display_name == "Cartão de Crédito"


def test_transaction_import_response_convert_string():
    """Test converting string to TransactionMethodSchema in ImportResponse"""
    response = TransactionImportResponse(
        date=date(2023, 10, 1),
        title="Test",
        amount=Decimal("50.00"),
        payment_method="pix",
    )
    assert isinstance(response.payment_method, TransactionMethodSchema)
    assert response.payment_method.value == "pix"
    assert response.payment_method.display_name == "Pix"


def test_transaction_import_response_convert_enum():
    """Test converting Enum to TransactionMethodSchema in ImportResponse"""
    response = TransactionImportResponse(
        date=date(2023, 10, 1),
        title="Test",
        amount=Decimal("50.00"),
        payment_method=TransactionMethod.DebitCard,
    )
    assert isinstance(response.payment_method, TransactionMethodSchema)
    assert response.payment_method.value == "debit_card"


def test_transaction_import_response_invalid_string():
    """Test invalid string returns None in ImportResponse"""
    response = TransactionImportResponse(
        date=date(2023, 10, 1),
        title="Test",
        amount=Decimal("50.00"),
        payment_method="invalid_method_xyz",
    )
    assert response.payment_method is None

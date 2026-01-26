import pytest
from uuid import uuid4
from decimal import Decimal
from datetime import date, datetime
from src.payments.model import (
    PaymentResponse,
    PaymentImportResponse,
    PaymentMethodSchema,
)
from src.entities.payment import PaymentMethod
from src.categories.model import CategoryResponse, CategoryType


def test_payment_response_convert_payment_method_enum():
    """Test converting PaymentMethod Enum to Schema in PaymentResponse"""
    category_data = CategoryResponse(
        id=uuid4(),
        name="Test Cat",
        slug="test-cat",
        type=CategoryType.EXPENSE,
        color_hex="#000000",
        is_active=True,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    response = PaymentResponse(
        id=uuid4(),
        user_id=uuid4(),
        title="Test",
        date=date(2023, 10, 1),
        amount=Decimal("100.00"),
        bank_id=uuid4(),
        category=category_data,
        payment_method=PaymentMethod.CreditCard,
        has_merchant=True,
    )

    assert isinstance(response.payment_method, PaymentMethodSchema)
    assert response.payment_method.value == "credit_card"
    assert response.payment_method.display_name == "Cartão de Crédito"


def test_payment_import_response_convert_string():
    """Test converting string to PaymentMethodSchema in ImportResponse"""
    response = PaymentImportResponse(
        date=date(2023, 10, 1),
        title="Test",
        amount=Decimal("50.00"),
        payment_method="pix",
    )
    assert isinstance(response.payment_method, PaymentMethodSchema)
    assert response.payment_method.value == "pix"
    assert response.payment_method.display_name == "Pix"


def test_payment_import_response_convert_enum():
    """Test converting Enum to PaymentMethodSchema in ImportResponse"""
    response = PaymentImportResponse(
        date=date(2023, 10, 1),
        title="Test",
        amount=Decimal("50.00"),
        payment_method=PaymentMethod.DebitCard,
    )
    assert isinstance(response.payment_method, PaymentMethodSchema)
    assert response.payment_method.value == "debit_card"


def test_payment_import_response_invalid_string():
    """Test invalid string returns None in ImportResponse"""
    response = PaymentImportResponse(
        date=date(2023, 10, 1),
        title="Test",
        amount=Decimal("50.00"),
        payment_method="invalid_method_xyz",
    )
    assert response.payment_method is None

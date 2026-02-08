import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
from src.open_finance import service
from src.entities.open_finance_item import OpenFinanceItem, ItemStatus
from src.entities.open_finance_account import OpenFinanceAccount, AccountType
from src.entities.category import Category
from src.entities.merchant import Merchant
from src.entities.merchant_alias import MerchantAlias
from src.entities.transaction import Transaction, TransactionMethod


@pytest.fixture
def mock_db_session():
    return MagicMock()


@pytest.fixture
def mock_pluggy_client():
    with patch("src.open_finance.service.client") as mock:
        yield mock


@pytest.mark.asyncio
def test_sync_transactions_success(mock_db_session, mock_pluggy_client):
    # Setup Data
    user_id = uuid.uuid4()
    item_id = uuid.uuid4()
    pluggy_item_id = "item-pluggy-123"

    # Mock Entities
    item = OpenFinanceItem(
        id=item_id,
        user_id=user_id,
        pluggy_item_id=pluggy_item_id,
        bank_id=uuid.uuid4(),
        status=ItemStatus.UPDATED,
    )

    account = OpenFinanceAccount(
        id=uuid.uuid4(),
        item_id=item_id,
        pluggy_account_id="acc-pluggy-123",
        name="Conta Teste",
        balance=100.0,
        type=AccountType.CHECKING,
        currency_code="BRL",
    )

    category = Category(
        id=uuid.uuid4(),
        pluggy_id="10000000",
        name="Groceries",
        slug="groceries",
        color_hex="#000000",
    )

    # Mock DB Query Responses
    # We mock query().filter().first() / all() chains
    # Simpler approach: specific mocks for specific entity types

    def side_effect_query(model):
        m = MagicMock()
        if model == OpenFinanceItem:
            m.filter.return_value.first.return_value = item
        elif model == OpenFinanceAccount:
            # First sync_accounts runs (using first()), then query accounts (using all())
            m.filter.return_value.all.return_value = [account]
            m.filter.return_value.first.return_value = account
        elif model == Category:
            m.all.return_value = [category]
        elif model == MerchantAlias:
            m.filter.return_value.first.return_value = None
        elif model == Merchant:
            m.filter.return_value.first.return_value = None
        elif model == Transaction:
            m.filter.return_value.first.return_value = None
        return m

    mock_db_session.query.side_effect = side_effect_query

    # Mock Pluggy Responses
    mock_pluggy_client.get_accounts = MagicMock(
        return_value=[
            {
                "id": "acc-pluggy-123",
                "name": "Conta Teste",
                "type": "CHECKING_ACCOUNT",
                "subtype": "CHECKING_ACCOUNT",
                "balance": 100.0,
                "currencyCode": "BRL",
            }
        ]
    )

    transaction_data = [
        {
            "id": "tx-123",
            "description": "Supermercado Extra",
            "amount": -50.00,
            "date": "2023-10-27T10:00:00.000Z",
            "categoryId": "10000000",
            "type": "DEBIT",
            "merchant": {"businessName": "Extra Hipermercados"},
        }
    ]
    mock_pluggy_client.get_transactions = MagicMock(return_value=transaction_data)

    # Execute
    service.sync_transactions_for_item(item_id, user_id, mock_db_session)

    # Assertions
    # 1. Accounts synced
    mock_pluggy_client.get_accounts.assert_called_with(pluggy_item_id)

    # 2. Transactions fetched
    mock_pluggy_client.get_transactions.assert_called_with("acc-pluggy-123")

    # 3. DB Adds
    added_instances = [call.args[0] for call in mock_db_session.add.call_args_list]

    assert any(isinstance(obj, MerchantAlias) for obj in added_instances)
    assert any(isinstance(obj, Merchant) for obj in added_instances)
    assert any(isinstance(obj, Transaction) for obj in added_instances)

    payment = next(obj for obj in added_instances if isinstance(obj, Transaction))
    assert payment.amount == 50.0
    assert payment.title == "Extra Hipermercados"
    assert payment.payment_method == PaymentMethod.DebitCard
    assert payment.category_id == category.id

import asyncio
from unittest.mock import MagicMock, patch
import uuid
from src.open_finance import service
from src.entities.open_finance_item import OpenFinanceItem, ItemStatus
from src.entities.open_finance_account import OpenFinanceAccount, AccountType
from src.entities.category import Category, CategoryType
from src.entities.merchant import Merchant
from src.entities.merchant_alias import MerchantAlias
from src.entities.payment import Payment, PaymentMethod


async def main():
    print("Starting debug...")
    mock_db_session = MagicMock()

    # Mock Data
    user_id = uuid.uuid4()
    item_id = uuid.uuid4()
    pluggy_item_id = "item-pluggy-123"

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
    )

    category = Category(
        id=uuid.uuid4(),
        pluggy_id="10000000",
        name="Groceries",
        slug="groceries",
        color_hex="#000000",
        type=CategoryType.EXPENSE,
    )

    def side_effect_query(model):
        m = MagicMock()
        if model == OpenFinanceItem:
            m.filter.return_value.first.return_value = item
        elif model == OpenFinanceAccount:
            m.filter.return_value.all.return_value = [account]
            m.filter.return_value.first.return_value = account
        elif model == Category:
            m.all.return_value = [category]
        elif model == MerchantAlias:
            m.filter.return_value.first.return_value = None
        elif model == Merchant:
            m.filter.return_value.first.return_value = None
        elif model == Payment:
            m.filter.return_value.first.return_value = None
        return m

    mock_db_session.query.side_effect = side_effect_query

    # Patch client
    with patch("src.open_finance.service.client") as mock_client:
        mock_client.get_accounts.return_value = [
            {
                "id": "acc-pluggy-123",
                "name": "Conta Teste",
                "type": "CHECKING_ACCOUNT",
                "subtype": "CHECKING_ACCOUNT",
                "balance": 100.0,
                "currencyCode": "BRL",
            }
        ]

        mock_client.get_transactions.return_value = [
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

        try:
            await service.sync_transactions_for_item(item_id, user_id, mock_db_session)
            print("Sync executed successfully.")

            added_instances = [
                call.args[0] for call in mock_db_session.add.call_args_list
            ]
            print(f"Added {len(added_instances)} instances.")
            for obj in added_instances:
                print(f"Added: {type(obj)}")

        except Exception as e:
            print(f"Caught exception: {e}")
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

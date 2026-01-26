import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from src.open_finance.service import (
    create_connect_token,
    get_transactions,
    sync_data,
)
from src.open_finance.model import ConnectTokenResponse, OpenFinanceTransaction


@pytest.mark.asyncio
async def test_create_connect_token_success():
    """
    Should return a ConnectTokenResponse when client call succeeds.
    """
    mock_token_data = {"accessToken": "valid-token-123"}

    with patch(
        "src.open_finance.service.client.create_connect_token", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_token_data

        response = await create_connect_token()

        assert isinstance(response, ConnectTokenResponse)
        assert response.access_token == "valid-token-123"
        mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_create_connect_token_failure():
    """
    Should raise HTTPException when client call fails.
    """
    with patch(
        "src.open_finance.service.client.create_connect_token", new_callable=AsyncMock
    ) as mock_create:
        mock_create.side_effect = Exception("API Error")

        with pytest.raises(HTTPException) as exc_info:
            await create_connect_token()

        assert exc_info.value.status_code == 500
        assert "API Error" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_get_transactions_success():
    """
    Should return a list of OpenFinanceTransaction when data is valid and connector matches.
    """
    item_id = "item-uuid"
    connector_id = 201

    # Mock Item response
    mock_item = {"id": item_id, "connector": {"id": 201, "name": "Nubank"}}

    # Mock Accounts response
    mock_accounts = [{"id": "acc-1", "name": "Conta Corrente", "number": "1234"}]

    # Mock Transactions response
    mock_txs = [
        {
            "id": "tx-1",
            "description": "Supermercado",
            "amount": -150.0,
            "date": "2023-10-25T10:00:00Z",
            "currency": "BRL",
        }
    ]

    with (
        patch(
            "src.open_finance.service.client.get_item", new_callable=AsyncMock
        ) as mock_get_item,
        patch(
            "src.open_finance.service.client.get_accounts", new_callable=AsyncMock
        ) as mock_get_accounts,
        patch(
            "src.open_finance.service.client.get_transactions", new_callable=AsyncMock
        ) as mock_get_txs,
    ):

        mock_get_item.return_value = mock_item
        mock_get_accounts.return_value = mock_accounts
        mock_get_txs.return_value = mock_txs

        result = await get_transactions(item_id, connector_id)

        assert len(result) == 1
        assert isinstance(result[0], OpenFinanceTransaction)
        assert result[0].description == "Supermercado"
        assert result[0].account_name == "Conta Corrente"

        # Verify calls
        mock_get_item.assert_called_once_with(item_id)
        mock_get_accounts.assert_called_once_with(item_id)
        mock_get_txs.assert_called_once_with("acc-1")


@pytest.mark.asyncio
async def test_get_transactions_connector_mismatch():
    """
    Should log a warning but proceed (or whatever the logic determines) when connector_id doesn't match.
    Currently logic passes, but let's verify it doesn't crash.
    """
    item_id = "item-uuid"
    connector_id = 999  # Mismatch

    mock_item = {"id": item_id, "connector": {"id": 201, "name": "Nubank"}}

    with (
        patch(
            "src.open_finance.service.client.get_item", new_callable=AsyncMock
        ) as mock_get_item,
        patch(
            "src.open_finance.service.client.get_accounts", new_callable=AsyncMock
        ) as mock_get_accounts,
    ):

        mock_get_item.return_value = mock_item
        mock_get_accounts.return_value = []  # No accounts to stop early

        # We expect it to run without error, just log warning (which we can capture if needed, but for now just success)
        result = await get_transactions(item_id, connector_id)
        assert result == []


@pytest.mark.asyncio
async def test_sync_data_success(db_session):
    """
    Should call sync_categories and sync_banks and return success message.
    """
    with (
        patch(
            "src.open_finance.service.sync_categories", new_callable=AsyncMock
        ) as mock_sync_cat,
        patch(
            "src.open_finance.service.sync_banks", new_callable=AsyncMock
        ) as mock_sync_bank,
    ):

        mock_sync_cat.return_value = None
        mock_sync_bank.return_value = None

        response = await sync_data(db_session)

        assert response == {"message": "Sincronização de dados concluída com sucesso"}
        mock_sync_cat.assert_called_once_with(db_session)
        mock_sync_bank.assert_called_once_with(db_session)


@pytest.mark.asyncio
async def test_sync_data_failure(db_session):
    """
    Should raise HTTPException if sync fails.
    """
    with patch(
        "src.open_finance.service.sync_categories", new_callable=AsyncMock
    ) as mock_sync_cat:
        mock_sync_cat.side_effect = Exception("Pluggy Down")

        with pytest.raises(HTTPException) as exc_info:
            await sync_data(db_session)


@pytest.mark.asyncio
async def test_create_item_success(db_session, test_user, token_data, sample_bank):
    """
    Should create a new Open Finance Item when bank exists.
    """
    from src.open_finance.model import CreateItemRequest, ItemResponse

    # Ensure sample_bank has connector_id set (fixture might need update if defaulting to None)
    # The fixture sets it? Let's check fixture or update bank here
    sample_bank.connector_id = 201
    db_session.add(sample_bank)
    db_session.commit()

    payload = CreateItemRequest(
        item_id="pluggy-item-uuid", connector_id=sample_bank.connector_id
    )

    with patch("src.open_finance.service.client", new_callable=AsyncMock):
        from src.open_finance.service import create_item

        response = await create_item(payload, token_data, db_session)

        assert isinstance(response, ItemResponse)
        assert response.pluggy_item_id == "pluggy-item-uuid"
        assert response.bank_name == "Nubank"
        assert response.status == "UPDATING"


@pytest.mark.asyncio
async def test_create_item_bank_not_found(db_session, token_data):
    """
    Should raise 404 if connector_id does not match any bank.
    """
    from src.open_finance.model import CreateItemRequest
    from src.open_finance.service import create_item

    payload = CreateItemRequest(item_id="pluggy-item-uuid", connector_id=9999)

    with pytest.raises(HTTPException) as exc_info:
        await create_item(payload, token_data, db_session)

    assert exc_info.value.status_code == 404
    assert "Banco não encontrado" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_sync_accounts_success(db_session, sample_bank, test_user):
    """
    Should fetch accounts from Pluggy and save to DB.
    """
    import uuid
    from src.entities.open_finance_account import OpenFinanceAccount, AccountType
    from src.entities.open_finance_item import OpenFinanceItem, ItemStatus
    from src.open_finance.service import sync_accounts

    # Setup: Create Item in DB
    item_id = uuid.uuid4()
    item = OpenFinanceItem(
        id=item_id,
        user_id=test_user.id,
        pluggy_item_id="pluggy-item-sync",
        bank_id=sample_bank.id,
        status=ItemStatus.UPDATED,
    )
    db_session.add(item)
    db_session.commit()

    mock_accounts = [
        {
            "id": "acc-1",
            "name": "Conta Corrente",
            "type": "CHECKING_ACCOUNT",
            "subtype": "CHECKING_ACCOUNT",
            "number": "1234",
            "balance": 1000.0,
            "currencyCode": "BRL",
        }
    ]

    with patch(
        "src.open_finance.service.client.get_accounts", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = mock_accounts

        await sync_accounts(item_id, "pluggy-item-sync", db_session)

        # Verify DB
        saved_acc = (
            db_session.query(OpenFinanceAccount)
            .filter_by(pluggy_account_id="acc-1")
            .first()
        )
        assert saved_acc is not None
        assert saved_acc.name == "Conta Corrente"
        assert saved_acc.type == AccountType.CHECKING
        assert saved_acc.balance == 1000.0
        assert saved_acc.item_id == item_id

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

# Assumes client fixture from conftest.py is automatically used or we use TestClient directly if mocking everything


def test_get_connect_token_route(client, auth_headers):
    """
    GET /open-finance/connect-token should return 200 and token.
    """
    mock_response = {"accessToken": "mocked-token-123"}

    # We patch the SERVICE function that the controller calls
    with patch(
        "src.open_finance.service.create_connect_token", new_callable=AsyncMock
    ) as mock_service:
        # The service returns a Pydantic model, need to match that or return dict if compatible?
        # Service returns ConnectTokenResponse object.
        from src.open_finance.model import ConnectTokenResponse

        mock_service.return_value = ConnectTokenResponse(accessToken="mocked-token-123")

        response = client.get("/open-finance/connect-token", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == {"accessToken": "mocked-token-123"}
        mock_service.assert_called_once()


def test_get_transactions_route(client, auth_headers):
    """
    GET /open-finance/transactions should accept Query Params and return list.
    """
    # Mock service return
    from src.open_finance.model import OpenFinanceTransaction

    mock_tx = OpenFinanceTransaction(
        id="tx-1",
        description="Demo Tx",
        amount=100.0,
        date="2023-01-01",
        currency="BRL",
    )

    with patch(
        "src.open_finance.service.get_transactions", new_callable=AsyncMock
    ) as mock_service:
        mock_service.return_value = [mock_tx]

        params = {"item_id": "item-123", "connector_id": 201}
        response = client.get(
            "/open-finance/transactions", params=params, headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "tx-1"
        assert data[0]["description"] == "Demo Tx"

        mock_service.assert_called_once_with("item-123", 201)


def test_get_transactions_validation_error(client, auth_headers):
    """
    GET /open-finance/transactions should return 422 if params missing.
    """
    response = client.get("/open-finance/transactions", headers=auth_headers)
    assert response.status_code == 422  # Missing query params


def test_sync_route(client, auth_headers):
    """
    POST /open-finance/sync should return 200 on success.
    """
    with patch(
        "src.open_finance.service.sync_data", new_callable=AsyncMock
    ) as mock_service:
        mock_service.return_value = {
            "message": "Sincronização de dados concluída com sucesso"
        }

        response = client.post("/open-finance/sync", headers=auth_headers)

        assert response.status_code == 200
        assert (
            response.json()["message"] == "Sincronização de dados concluída com sucesso"
        )


def test_create_item_route(client, auth_headers):
    """
    POST /open-finance/items should return 200 and created Item.
    """
    from src.open_finance.model import ItemResponse

    mock_resp = ItemResponse(
        id="item-uuid",
        pluggy_item_id="pluggy-id",
        bank_name="Nubank",
        status="UPDATING",
    )

    with patch(
        "src.open_finance.service.create_item", new_callable=AsyncMock
    ) as mock_service:
        mock_service.return_value = mock_resp

        payload = {"itemId": "pluggy-id", "connectorId": 201}
        response = client.post(
            "/open-finance/items", json=payload, headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "item-uuid"
        assert data["pluggyItemId"] == "pluggy-id"
        mock_service.assert_called_once()

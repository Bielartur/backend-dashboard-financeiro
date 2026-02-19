import pytest
from httpx import AsyncClient
from datetime import date
from decimal import Decimal
from src.entities.transaction import TransactionMethod


@pytest.mark.asyncio
async def test_create_transaction_api(
    client: AsyncClient, auth_headers, sample_bank, sample_category
):
    payload = {
        "title": "API Transaction",
        "date": str(date.today()),
        "amount": -50.00,
        "payment_method": TransactionMethod.Pix.value,
        "bank_id": str(sample_bank.id),
        "category_id": str(sample_category.id),
    }
    response = await client.post("/transactions/", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "API Transaction"


@pytest.mark.asyncio
async def test_get_transactions_api(client: AsyncClient, auth_headers):
    response = await client.get("/transactions/search", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["items"] is not None  # Paginated


@pytest.mark.asyncio
async def test_get_transaction_by_id_api(
    client: AsyncClient, auth_headers, sample_bank, sample_category
):
    # Create
    payload = {
        "title": "To Fetch",
        "date": str(date.today()),
        "amount": -10.00,
        "payment_method": TransactionMethod.Pix.value,
        "bank_id": str(sample_bank.id),
        "category_id": str(sample_category.id),
    }
    create_res = await client.post("/transactions/", json=payload, headers=auth_headers)
    t_id = create_res.json()["id"]

    # Fetch
    response = await client.get(f"/transactions/{t_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["title"] == "To Fetch"


@pytest.mark.asyncio
async def test_update_transaction_api(
    client: AsyncClient, auth_headers, sample_bank, sample_category
):
    # Create
    payload = {
        "title": "To Update",
        "date": str(date.today()),
        "amount": -10.00,
        "payment_method": TransactionMethod.Pix.value,
        "bank_id": str(sample_bank.id),
        "category_id": str(sample_category.id),
    }

    create_res = await client.post("/transactions/", json=payload, headers=auth_headers)
    t_id = create_res.json()["id"]

    # Update
    update_payload = {"title": "Updated Title"}
    response = await client.put(
        f"/transactions/{t_id}", json=update_payload, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Title"


@pytest.mark.asyncio
async def test_delete_transaction_api(
    client: AsyncClient, auth_headers, sample_bank, sample_category
):
    # Create
    payload = {
        "title": "To Delete",
        "date": str(date.today()),
        "amount": -10.00,
        "payment_method": TransactionMethod.Pix.value,
        "bank_id": str(sample_bank.id),
        "category_id": str(sample_category.id),
    }
    create_res = await client.post("/transactions/", json=payload, headers=auth_headers)
    t_id = create_res.json()["id"]

    # Delete
    response = await client.delete(f"/transactions/{t_id}", headers=auth_headers)
    assert response.status_code == 204

    # Verify
    get_res = await client.get(f"/transactions/{t_id}", headers=auth_headers)
    assert get_res.status_code == 404

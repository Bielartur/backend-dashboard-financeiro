import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.mark.asyncio
async def test_create_bank_admin_success(
    client: AsyncClient, admin_auth_headers, db_session
):
    payload = {
        "name": "New Bank",
        "slug": "new-bank",
        "color_hex": "#000000",
        "logo_url": "http://example.com/logo.png",
    }
    response = await client.post("/banks/", json=payload, headers=admin_auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "New Bank"


@pytest.mark.asyncio
async def test_create_bank_user_unauthorized(client: AsyncClient, auth_headers):
    payload = {
        "name": "User Bank",
        "slug": "user-bank",
        "color_hex": "#FFFFFF",
        "logo_url": "http://example.com/logo.png",
    }
    response = await client.post("/banks/", json=payload, headers=auth_headers)
    assert response.status_code == 403  # Expect explicit Forbidden for non-admin


@pytest.mark.asyncio
async def test_get_banks_success(client: AsyncClient, auth_headers, sample_bank):
    response = await client.get("/banks/", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(b["id"] == str(sample_bank.id) for b in data)


@pytest.mark.asyncio
async def test_update_bank_admin_success(
    client: AsyncClient, admin_auth_headers, sample_bank
):
    payload = {"name": "Updated Bank", "color_hex": "#123456"}
    response = await client.put(
        f"/banks/{sample_bank.id}", json=payload, headers=admin_auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Bank"


@pytest.mark.asyncio
async def test_delete_bank_admin_success(
    client: AsyncClient, admin_auth_headers, sample_bank
):
    response = await client.delete(
        f"/banks/{sample_bank.id}", headers=admin_auth_headers
    )
    assert response.status_code == 204

    # Verify deletion
    response = await client.get(f"/banks/{sample_bank.id}", headers=admin_auth_headers)
    assert response.status_code == 404

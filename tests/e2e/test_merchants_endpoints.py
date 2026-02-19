import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.mark.asyncio
async def test_create_merchant_success(client: AsyncClient, auth_headers):
    payload = {"name": "New Merchant"}
    response = await client.post("/merchants/", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "New Merchant"
    assert "id" in data


@pytest.mark.asyncio
async def test_get_merchants_success(client: AsyncClient, auth_headers):
    # Create one first
    await client.post("/merchants/", json={"name": "Merchant 1"}, headers=auth_headers)

    response = await client.get("/merchants/", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_get_merchant_by_id_success(client: AsyncClient, auth_headers):
    create_res = await client.post(
        "/merchants/", json={"name": "To Fetch"}, headers=auth_headers
    )
    m_id = create_res.json()["id"]

    response = await client.get(f"/merchants/{m_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["name"] == "To Fetch"


@pytest.mark.asyncio
async def test_update_merchant_success(client: AsyncClient, auth_headers):
    create_res = await client.post(
        "/merchants/", json={"name": "To Update"}, headers=auth_headers
    )
    m_id = create_res.json()["id"]

    payload = {"name": "Updated Name"}
    response = await client.put(
        f"/merchants/{m_id}", json=payload, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_delete_merchant_success(client: AsyncClient, auth_headers):
    create_res = await client.post(
        "/merchants/", json={"name": "To Delete"}, headers=auth_headers
    )
    m_id = create_res.json()["id"]

    response = await client.delete(f"/merchants/{m_id}", headers=auth_headers)
    assert response.status_code == 204

    # Verify gone
    get_res = await client.get(f"/merchants/{m_id}", headers=auth_headers)
    assert get_res.status_code == 404

import pytest
from httpx import AsyncClient
from uuid import uuid4
from src.entities.merchant import Merchant
from src.entities.merchant_alias import MerchantAlias
from src.merchants import service as merchant_service
from src.merchants import model as merchant_model
from src.auth.model import TokenData


@pytest.fixture
async def sample_alias(db_session, test_user):
    alias = MerchantAlias(id=uuid4(), pattern="Uber", user_id=test_user.id)
    db_session.add(alias)
    await db_session.commit()
    return alias


@pytest.mark.asyncio
async def test_get_aliases(client: AsyncClient, auth_headers, sample_alias):
    response = await client.get("/aliases/", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["items"][0]["pattern"] == "Uber"


@pytest.mark.asyncio
async def test_create_alias_group(
    client: AsyncClient, auth_headers, db_session, test_user, token_data
):
    # Create merchants first
    m1_data = merchant_model.MerchantCreate(name="Uber Trip")
    m1 = await merchant_service.create_merchant(token_data, db_session, m1_data)

    payload = {"pattern": "Uber", "merchantIds": [str(m1.id)], "categoryId": None}

    response = await client.post(
        "/aliases/set_group", json=payload, headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["pattern"] == "Uber"


@pytest.mark.asyncio
async def test_update_alias(client: AsyncClient, auth_headers, sample_alias):
    payload = {"pattern": "Uber Updated"}
    response = await client.put(
        f"/aliases/{sample_alias.id}", json=payload, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["pattern"] == "Uber Updated"


@pytest.mark.asyncio
async def test_append_merchant(
    client: AsyncClient, auth_headers, sample_alias, db_session, test_user, token_data
):
    m1_data = merchant_model.MerchantCreate(name="Uber Eats")
    m1 = await merchant_service.create_merchant(token_data, db_session, m1_data)

    response = await client.post(
        f"/aliases/{sample_alias.id}/append/{m1.id}", headers=auth_headers
    )
    assert response.status_code == 201

    # Verify via API
    get_response = await client.get(f"/aliases/{sample_alias.id}", headers=auth_headers)
    assert any(m["id"] == str(m1.id) for m in get_response.json()["merchants"])


@pytest.mark.asyncio
async def test_remove_merchant(
    client: AsyncClient, auth_headers, sample_alias, db_session, test_user, token_data
):
    m1_data = merchant_model.MerchantCreate(name="Uber Eats")
    m1 = await merchant_service.create_merchant(token_data, db_session, m1_data)

    # Manually associate for the test setup (since create_merchant doesn't support adding alias_id directly in Create model yet?
    # checking model.py: class MerchantCreate(MerchantBase): merchant_alias_id: Optional[UUID] = None
    # So we can pass it!)

    # Wait, create_merchant takes MerchantCreate which HAS merchant_alias_id.
    # Let's verify src/merchants/model.py again. Yes it has.
    # But wait, MerchantCreate has merchant_alias_id, but does create_merchant logic use it?
    # src/merchants/service.py: new_merchant = Merchant(**merchant.model_dump())
    # Yes it does.

    # Actually, let's just update the merchant alias id after creation if needed, or pass it in create
    # But wait, to be safe and consistent with previous code

    # Refactoring to use create_merchant with alias_id if possible, or update.
    m1.merchant_alias_id = sample_alias.id
    db_session.add(m1)
    await db_session.commit()

    response = await client.delete(
        f"/aliases/{sample_alias.id}/remove/{m1.id}", headers=auth_headers
    )
    assert response.status_code == 204

    # Verify removal
    get_response = await client.get(f"/aliases/{sample_alias.id}", headers=auth_headers)

    assert get_response.status_code == 404
    assert "não encontrado" in get_response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_search_aliases(client: AsyncClient, auth_headers, sample_alias):
    response = await client.get("/aliases/search?query=Uber", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["pattern"] == "Uber"

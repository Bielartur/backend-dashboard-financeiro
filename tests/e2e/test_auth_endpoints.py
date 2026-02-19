import pytest
from httpx import AsyncClient
from src.entities.user import User
from src.auth.service import get_password_hash, create_access_token
from uuid import uuid4
from datetime import timedelta

# Endpoint URIs
REGISTER_URL = "/auth/register"
LOGIN_URL = "/auth/login"
REFRESH_URL = "/auth/refresh"
ME_URL = "/auth/me"
LOGOUT_URL = "/auth/logout"


# ==================== Register ====================


@pytest.mark.asyncio
async def test_register_user_success(client: AsyncClient, db_session):
    payload = {
        "email": "newuser@example.com",
        "password": "password123",
        "firstName": "New",
        "lastName": "User",
    }
    response = await client.post(REGISTER_URL, json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == payload["email"]
    assert "id" in data


# ==================== Login ====================


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, db_session):
    password = "password123"
    user = User(
        id=uuid4(),
        email="login@example.com",
        password_hash=get_password_hash(password),
        first_name="Login",
        last_name="User",
    )
    db_session.add(user)
    await db_session.commit()

    form_data = {"username": user.email, "password": password}
    response = await client.post(LOGIN_URL, data=form_data)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "refresh_token" in response.cookies


@pytest.mark.asyncio
async def test_login_failure(client: AsyncClient):
    form_data = {"username": "wrong@example.com", "password": "wrongpassword"}
    response = await client.post(LOGIN_URL, data=form_data)
    assert response.status_code == 401


# ==================== Refresh ====================


@pytest.mark.asyncio
async def test_refresh_token_success(client: AsyncClient, db_session):
    password = "password123"
    user = User(
        id=uuid4(),
        email="refresh@example.com",
        password_hash=get_password_hash(password),
        first_name="Refresh",
        last_name="User",
    )
    db_session.add(user)
    await db_session.commit()

    form_data = {"username": user.email, "password": password}
    login_response = await client.post(LOGIN_URL, data=form_data)
    refresh_token = login_response.cookies["refresh_token"]

    client.cookies.set("refresh_token", refresh_token)
    response = await client.post(REFRESH_URL)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in response.cookies
    assert response.cookies["refresh_token"] != refresh_token  # Rotated


@pytest.mark.asyncio
async def test_refresh_without_cookie(client: AsyncClient):
    """No refresh_token cookie → 401."""
    client.cookies.clear()
    response = await client.post(REFRESH_URL)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_invalid_token(client: AsyncClient):
    """Invalid refresh_token cookie → 401."""
    client.cookies.set("refresh_token", "invalid.token.value")
    response = await client.post(REFRESH_URL)
    assert response.status_code == 401


# ==================== /me ====================


@pytest.mark.asyncio
async def test_get_current_user_success(client: AsyncClient, auth_headers):
    response = await client.get(ME_URL, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "itemIds" in data


@pytest.mark.asyncio
async def test_get_me_unauthenticated(client: AsyncClient):
    """No auth header → 401."""
    response = await client.get(ME_URL)
    assert response.status_code == 401


# ==================== Logout ====================


@pytest.mark.asyncio
async def test_logout_success(client: AsyncClient, db_session):
    password = "password123"
    user = User(
        id=uuid4(),
        email="logout@example.com",
        password_hash=get_password_hash(password),
        first_name="Logout",
        last_name="User",
    )
    db_session.add(user)
    await db_session.commit()

    form_data = {"username": user.email, "password": password}
    login_response = await client.post(LOGIN_URL, data=form_data)
    refresh_token = login_response.cookies["refresh_token"]

    client.cookies.set("refresh_token", refresh_token)
    response = await client.post(LOGOUT_URL)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_logout_without_cookie(client: AsyncClient):
    """No refresh_token cookie → 401."""
    client.cookies.clear()
    response = await client.post(LOGOUT_URL)
    assert response.status_code == 401

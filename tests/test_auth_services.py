import pytest
from datetime import timedelta, datetime, timezone
from uuid import uuid4
from unittest.mock import patch
import jwt
from src.auth.service import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    verify_token,
    verify_refresh_token,
    verify_password,
    get_password_hash,
    get_current_user,
    get_current_user_from_db,
    get_current_admin,
    login_for_access_token,
    refresh_access_token,
    register_user,
    ALGORITHM,
    SECRET_KEY,
)
from src.entities.user import User
from src.auth.model import TokenData, RegisterUserRequest, Token
from src.exceptions.auth import AuthenticationError
from fastapi import HTTPException


# ==================== Password Utilities ====================


def test_verify_password_success():
    hashed = get_password_hash("password123")
    assert verify_password("password123", hashed) is True


def test_verify_password_failure():
    hashed = get_password_hash("password123")
    assert verify_password("wrongpassword", hashed) is False


# ==================== TokenData Model ====================


def test_token_data_get_uuid():
    user_id = uuid4()
    td = TokenData(user_id=str(user_id))
    assert td.get_uuid() == user_id


def test_token_data_get_uuid_none():
    td = TokenData(user_id=None)
    assert td.get_uuid() is None


# ==================== create_access_token ====================


def test_create_access_token():
    user_id = uuid4()
    token = create_access_token(
        email="test@test.com", user_id=user_id, expires_delta=timedelta(minutes=15)
    )
    decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert decoded["sub"] == "test@test.com"
    assert decoded["id"] == str(user_id)
    assert decoded["type"] == "access"
    assert "exp" in decoded
    assert "jti" in decoded


def test_create_access_token_default_expiry():
    token = create_access_token(email="test@test.com", user_id=uuid4())
    decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert decoded["sub"] == "test@test.com"


# ==================== create_refresh_token ====================


def test_create_refresh_token():
    user_id = uuid4()
    token = create_refresh_token(
        email="test@test.com", user_id=user_id, expires_delta=timedelta(days=30)
    )
    decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert decoded["sub"] == "test@test.com"
    assert decoded["id"] == str(user_id)
    assert decoded["type"] == "refresh"


# ==================== verify_token ====================


def test_verify_token_success():
    user_id = uuid4()
    token = create_access_token(email="test@test.com", user_id=user_id)
    result = verify_token(token)
    assert result.user_id == str(user_id)


def test_verify_token_expired():
    user_id = uuid4()
    token = create_access_token(
        email="test@test.com",
        user_id=user_id,
        expires_delta=timedelta(seconds=-1),
    )
    with pytest.raises(AuthenticationError) as exc_info:
        verify_token(token)
    assert exc_info.value.detail == "Token expirado"


def test_verify_token_invalid():
    with pytest.raises(AuthenticationError) as exc_info:
        verify_token("invalid.token.string")
    assert exc_info.value.detail == "Token inválido"


def test_verify_token_tampered():
    user_id = uuid4()
    token = create_access_token(email="test@test.com", user_id=user_id)
    # Tamper with the token
    tampered_token = token + "x"
    with pytest.raises(AuthenticationError) as exc_info:
        verify_token(tampered_token)
    assert exc_info.value.detail == "Token inválido"


# ==================== verify_refresh_token ====================


def test_verify_refresh_token_success():
    user_id = uuid4()
    token = create_refresh_token(email="test@test.com", user_id=user_id)
    result = verify_refresh_token(token)
    assert result.user_id == str(user_id)


def test_verify_refresh_token_expired():
    user_id = uuid4()
    token = create_refresh_token(
        email="test@test.com",
        user_id=user_id,
        expires_delta=timedelta(seconds=-1),
    )
    with pytest.raises(AuthenticationError) as exc_info:
        verify_refresh_token(token)
    assert exc_info.value.detail == "Refresh token expirado"


def test_verify_refresh_token_wrong_type():
    """Using an access token as a refresh token should fail."""
    user_id = uuid4()
    access_token = create_access_token(email="test@test.com", user_id=user_id)
    with pytest.raises(AuthenticationError) as exc_info:
        verify_refresh_token(access_token)
    assert exc_info.value.detail == "Refresh token inválido"


def test_verify_refresh_token_invalid():
    with pytest.raises(AuthenticationError) as exc_info:
        verify_refresh_token("garbage.token.string")
    assert exc_info.value.detail == "Refresh token inválido"


# ==================== authenticate_user ====================


@pytest.mark.asyncio
async def test_authenticate_user_success(db_session):
    user_id = uuid4()
    user = User(
        id=user_id,
        email="auth@test.com",
        password_hash=get_password_hash("password123"),
        first_name="Test",
        last_name="User",
    )
    db_session.add(user)
    await db_session.commit()

    authenticated_user = await authenticate_user(
        "auth@test.com", "password123", db_session
    )
    assert authenticated_user.id == user_id


@pytest.mark.asyncio
async def test_authenticate_user_wrong_email(db_session):
    result = await authenticate_user("nonexistent@test.com", "password", db_session)
    assert result is False


@pytest.mark.asyncio
async def test_authenticate_user_wrong_password(db_session):
    user = User(
        id=uuid4(),
        email="wrong_pw@test.com",
        password_hash=get_password_hash("correctpassword"),
        first_name="Test",
        last_name="User",
    )
    db_session.add(user)
    await db_session.commit()

    result = await authenticate_user("wrong_pw@test.com", "wrongpassword", db_session)
    assert result is False


# ==================== register_user ====================


@pytest.mark.asyncio
async def test_register_user_success(db_session):
    request = RegisterUserRequest(
        email="newuser@test.com",
        first_name="New",
        last_name="User",
        password="password123",
    )
    user = await register_user(db_session, request)
    assert user is not None
    assert user.email == "newuser@test.com"
    assert user.is_admin is False


@pytest.mark.asyncio
async def test_register_user_super_admin(db_session, monkeypatch):
    monkeypatch.setenv("SUPER_ADMIN_EMAIL", "admin@super.com")
    # Reload os.getenv for the patched env
    request = RegisterUserRequest(
        email="admin@super.com",
        first_name="Super",
        last_name="Admin",
        password="admin123",
    )
    user = await register_user(db_session, request)
    assert user.is_admin is True


@pytest.mark.asyncio
async def test_register_user_duplicate_email_raises(db_session):
    request = RegisterUserRequest(
        email="duplicate@test.com",
        first_name="First",
        last_name="User",
        password="password123",
    )
    await register_user(db_session, request)

    # Try registering with the same email
    with pytest.raises(Exception):
        await register_user(db_session, request)


# ==================== get_current_user ====================


def test_get_current_user_returns_token_data():
    user_id = uuid4()
    token = create_access_token(email="test@test.com", user_id=user_id)
    result = get_current_user(token)
    assert isinstance(result, TokenData)
    assert result.user_id == str(user_id)


# ==================== get_current_user_from_db ====================


@pytest.mark.asyncio
async def test_get_current_user_from_db_success(db_session):
    user_id = uuid4()
    user = User(
        id=user_id,
        email="current@test.com",
        password_hash="hash",
        first_name="Test",
        last_name="User",
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(email=user.email, user_id=user.id)
    current_user = await get_current_user_from_db(token, db_session)
    assert current_user.id == user_id


@pytest.mark.asyncio
async def test_get_current_user_from_db_not_found(db_session):
    """Valid token but user was deleted from DB."""
    user_id = uuid4()
    token = create_access_token(email="deleted@test.com", user_id=user_id)

    with pytest.raises(AuthenticationError) as exc_info:
        await get_current_user_from_db(token, db_session)
    assert exc_info.value.detail == "User not found"


# ==================== get_current_admin ====================


@pytest.mark.asyncio
async def test_get_current_admin_success(db_session):
    user = User(
        id=uuid4(),
        email="admin@test.com",
        password_hash="hash",
        first_name="Admin",
        last_name="User",
        is_admin=True,
    )
    db_session.add(user)
    await db_session.commit()

    result = await get_current_admin(user)
    assert result.is_admin is True
    assert result.id == user.id


@pytest.mark.asyncio
async def test_get_current_admin_forbidden(db_session):
    user = User(
        id=uuid4(),
        email="nonadmin@test.com",
        password_hash="hash",
        first_name="Regular",
        last_name="User",
        is_admin=False,
    )
    db_session.add(user)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_admin(user)
    assert exc_info.value.status_code == 403


# ==================== login_for_access_token ====================


@pytest.mark.asyncio
async def test_login_for_access_token_success(db_session):
    user = User(
        id=uuid4(),
        email="login@test.com",
        password_hash=get_password_hash("password123"),
        first_name="Login",
        last_name="User",
    )
    db_session.add(user)
    await db_session.commit()

    class FakeForm:
        username = "login@test.com"
        password = "password123"

    token_response, refresh_token = await login_for_access_token(FakeForm(), db_session)
    assert token_response.access_token is not None
    assert token_response.token_type == "bearer"
    assert refresh_token is not None


@pytest.mark.asyncio
async def test_login_for_access_token_failure(db_session):
    class FakeForm:
        username = "nonexistent@test.com"
        password = "wrongpassword"

    with pytest.raises(AuthenticationError):
        await login_for_access_token(FakeForm(), db_session)


@pytest.mark.asyncio
async def test_login_super_admin_promotion(db_session, monkeypatch):
    """User with super admin email but is_admin=False should be promoted on login."""
    monkeypatch.setenv("SUPER_ADMIN_EMAIL", "promote@test.com")

    user = User(
        id=uuid4(),
        email="promote@test.com",
        password_hash=get_password_hash("password123"),
        first_name="Promote",
        last_name="User",
        is_admin=False,
    )
    db_session.add(user)
    await db_session.commit()

    class FakeForm:
        username = "promote@test.com"
        password = "password123"

    token_response, refresh_token = await login_for_access_token(FakeForm(), db_session)
    assert token_response.access_token is not None

    # Verify user was promoted
    await db_session.refresh(user)
    assert user.is_admin is True


# ==================== refresh_access_token ====================


@pytest.mark.asyncio
async def test_refresh_access_token_success(db_session):
    user_id = uuid4()
    email = "refresh@test.com"
    user = User(
        id=user_id,
        email=email,
        password_hash="hash",
        first_name="Refresh",
        last_name="User",
    )
    db_session.add(user)
    await db_session.commit()

    refresh_token = create_refresh_token(email, user_id, timedelta(days=1))

    new_token, new_refresh = await refresh_access_token(refresh_token, db_session)
    assert new_token.access_token is not None
    assert new_token.token_type == "bearer"
    assert new_refresh is not None
    assert new_refresh != refresh_token


@pytest.mark.asyncio
async def test_refresh_access_token_user_not_found(db_session):
    """Valid refresh token but user was deleted."""
    user_id = uuid4()
    refresh_token = create_refresh_token("deleted@test.com", user_id, timedelta(days=1))

    with pytest.raises(AuthenticationError) as exc_info:
        await refresh_access_token(refresh_token, db_session)
    assert exc_info.value.detail == "Usuário não encontrado"

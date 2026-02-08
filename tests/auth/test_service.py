from datetime import timedelta
from uuid import uuid4, UUID
from src.auth.service import (
    create_refresh_token,
    verify_refresh_token,
    create_access_token,
    verify_token,
    refresh_access_token,
    authenticate_user,
    get_password_hash,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
)
from src.exceptions.auth import AuthenticationError
from src.entities.user import User
import pytest
from unittest.mock import MagicMock
from sqlalchemy.orm import Session
import jwt
from src.auth.service import SECRET_KEY, ALGORITHM

# ========== Service Tests ==========


def test_refresh_token_lifecycle():
    user_id = uuid4()
    email = "test@example.com"

    # Create
    token = create_refresh_token(email, user_id)
    assert token is not None

    # Verify
    token_data = verify_refresh_token(token)
    assert token_data.user_id == str(user_id)


def test_refresh_token_invalid_type():
    user_id = uuid4()
    email = "test@example.com"

    # Create ACCESS token
    token = create_access_token(email, user_id)

    # Verify as REFRESH token should fail
    with pytest.raises(AuthenticationError) as excinfo:
        verify_refresh_token(token)

    assert "Refresh token inválido" in str(
        excinfo.value
    ) or "Invalid token type" in str(excinfo.value)


def test_access_token_expiration():
    user_id = uuid4()
    email = "expire@test.com"
    # Create expired token (-1 minute)
    token = create_access_token(email, user_id, timedelta(minutes=-1))

    with pytest.raises(AuthenticationError) as excinfo:
        verify_token(token)
    assert "Token expirado" in str(excinfo.value)


def test_refresh_token_expiration():
    user_id = uuid4()
    email = "expire_refresh@test.com"
    # Create expired token (-1 minute)
    token = create_refresh_token(email, user_id, timedelta(minutes=-1))

    with pytest.raises(AuthenticationError) as excinfo:
        verify_refresh_token(token)
    assert "Refresh token expirado" in str(excinfo.value)


def test_refresh_access_token_logic():
    # Mock DB
    mock_db = MagicMock(spec=Session)
    user_id = uuid4()
    user = User(
        id=user_id,
        email="rotate@test.com",
        password_hash="hash",
        first_name="Test",
        last_name="User",
    )

    # Setup mock query
    mock_db.query.return_value.filter.return_value.first.return_value = user

    # Create valid refresh token
    refresh_token = create_refresh_token(user.email, user_id, timedelta(days=1))

    # Call refresh logic
    new_access_token_model, new_refresh_token = refresh_access_token(
        refresh_token, mock_db
    )

    assert new_access_token_model.access_token is not None
    assert new_access_token_model.token_type == "bearer"
    assert new_refresh_token is not None
    assert new_refresh_token != refresh_token  # Should be rotated (different exp)


def test_refresh_access_token_uuser_not_found():
    mock_db = MagicMock(spec=Session)
    user_id = uuid4()

    # Setup mock query to return None (user deleted/suspended)
    mock_db.query.return_value.filter.return_value.first.return_value = None

    refresh_token = create_refresh_token("deleted@test.com", user_id, timedelta(days=1))

    with pytest.raises(AuthenticationError) as exc:
        refresh_access_token(refresh_token, mock_db)
    assert "Usuário não encontrado" in str(exc.value)

import pytest
import sys
import os

# Add project root to sys.path so we can import from main.py and src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from main import app
from src.database.core import get_db, Base
from src.auth.service import create_access_token, get_password_hash
from src.auth.model import TokenData
from src.entities.user import User
from src.entities.bank import Bank
from datetime import timedelta
import uuid

# Setup In-Memory SQLite Database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """
    Creates a fresh database session for a test.
    """
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    """
    Dependency override for database and TestClient creation.
    """

    def override_get_db():
        try:
            yield db_session
        finally:
            pass  # Session is closed in the db_session fixture

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="function")
def test_user(db_session):
    """
    Creates a test user and returns it.
    """
    user = User(
        email="test@example.com",
        password_hash=get_password_hash("password123"),
        first_name="Test",
        last_name="User",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def auth_headers(test_user):
    """
    Returns valid authorization headers for the test user.
    """
    access_token = create_access_token(
        email=test_user.email, user_id=test_user.id, expires_delta=timedelta(minutes=30)
    )
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture(scope="function")
def token_data(test_user):
    """
    Returns a TokenData instance for the test user.
    """
    return TokenData(user_id=str(test_user.id))


@pytest.fixture(scope="function")
def sample_bank(db_session):
    bank = Bank(
        name="Nubank",
        slug="nubank",
        logo_url="http://example.com/nubank.png",
        color_hex="#8A05BE",
    )
    db_session.add(bank)
    db_session.commit()
    db_session.refresh(bank)
    return bank

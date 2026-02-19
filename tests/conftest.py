import pytest
import sys
import os
import asyncio
from typing import AsyncGenerator

# Add project root to sys.path so we can import from main.py and src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import select
from httpx import AsyncClient, ASGITransport
from main import app
from src.database.core import get_db, Base
from src.auth.service import create_access_token, get_password_hash
from src.auth.model import TokenData
from src.entities.user import User
from src.entities.bank import Bank
from datetime import timedelta
import uuid

# Setup In-Memory SQLite Database for testing (Async)
SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = async_sessionmaker(
    autocommit=False, autoflush=False, bind=engine, expire_on_commit=False
)


@pytest.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Creates a fresh database session for a test.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(scope="function")
async def client(db_session):
    """
    Dependency override for database and AsyncClient creation.
    """

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # Disable lifespan to prevent main.py from trying to use the real DB engine
    # We manage DB tables via the db_session fixture
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = noop_lifespan

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c

    # Restore (though usually not strictly needed as app is module global but we want to be clean)
    app.router.lifespan_context = original_lifespan
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
async def test_user(db_session):
    """
    Creates a test user and returns it.
    """
    user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        password_hash=get_password_hash("password123"),
        first_name="Test",
        last_name="User",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
async def test_admin(db_session):
    """
    Creates a test admin user and returns it.
    """
    user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        password_hash=get_password_hash("admin123"),
        first_name="Admin",
        last_name="User",
        is_admin=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
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
def admin_auth_headers(test_admin):
    """
    Returns valid authorization headers for the test admin.
    """
    access_token = create_access_token(
        email=test_admin.email,
        user_id=test_admin.id,
        expires_delta=timedelta(minutes=30),
    )
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture(scope="function")
def token_data(test_user):
    """
    Returns a TokenData instance for the test user.
    """
    return TokenData(user_id=str(test_user.id))


@pytest.fixture(scope="function")
async def sample_bank(db_session):
    bank = Bank(
        id=uuid.uuid4(),
        name="Nubank",
        slug="nubank",
        logo_url="http://example.com/nubank.png",
        color_hex="#8A05BE",
    )
    db_session.add(bank)
    await db_session.commit()
    await db_session.refresh(bank)
    return bank


from src.entities.category import Category


@pytest.fixture(scope="function")
async def sample_category(db_session):
    category = Category(
        id=uuid.uuid4(),
        name="Food",
        slug="food",
        color_hex="#FF0000",
    )
    db_session.add(category)
    await db_session.commit()
    await db_session.refresh(category)
    return category


@pytest.fixture(scope="function")
async def sample_merchant(db_session, token_data):
    from src.merchants import service
    from src.merchants.model import MerchantCreate

    # Service ensures alias creation/linking logic
    merchant_create = MerchantCreate(name="Uber")
    return await service.create_merchant(token_data, db_session, merchant_create)


@pytest.fixture(scope="function")
async def sample_merchant_alias(sample_merchant, db_session):
    # Return the alias created/linked by the merchant service
    if not sample_merchant.merchant_alias:
        # Fetch if needed (e.g. if not eager loaded)
        from src.entities.merchant_alias import MerchantAlias
        from sqlalchemy import select

        result = await db_session.execute(
            select(MerchantAlias).filter(
                MerchantAlias.id == sample_merchant.merchant_alias_id
            )
        )
        return result.scalars().first()
    return sample_merchant.merchant_alias

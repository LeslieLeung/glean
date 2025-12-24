"""Global pytest fixtures for testing."""

import asyncio
import contextlib
import os
from collections.abc import AsyncGenerator, Generator
from typing import Any

import dotenv
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from glean_api.main import app
from glean_database import Base
from glean_database.models.user import User
from glean_database.session import get_session

with contextlib.suppress(OSError):
    dotenv.load_dotenv()


class MockArqRedis:
    """Mock ArqRedis for testing."""

    def __init__(self):
        self.enqueued_jobs: list[tuple[str, tuple[Any, ...]]] = []

    async def enqueue_job(self, func_name: str, *args: Any, **kwargs: Any) -> None:
        """Mock enqueue_job that records calls without actually queuing."""
        self.enqueued_jobs.append((func_name, args))


# Global mock redis instance for testing
mock_redis = MockArqRedis()

# Test database URL - check TEST_DATABASE_URL first, then DATABASE_URL, then fallback to default
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    os.getenv("DATABASE_URL", "postgresql+asyncpg://glean:devpassword@localhost:5433/glean_test"),
)

# Safety check: ensure tests only run on a test database
if "_test" not in TEST_DATABASE_URL and "/test" not in TEST_DATABASE_URL:
    raise RuntimeError(
        f"Safety check failed: TEST_DATABASE_URL must point to a test database "
        f"(name should contain 'test'). Current: {TEST_DATABASE_URL}"
    )


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for session scope."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=NullPool,  # Disable connection pooling for tests
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    # Create connection
    async with test_engine.connect() as connection:
        # Start outer transaction
        transaction = await connection.begin()

        # Create session bound to the connection
        async_session = async_sessionmaker(
            bind=connection,
            class_=AsyncSession,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )

        async with async_session() as session:
            yield session

            # Rollback the outer transaction
            await transaction.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client with database and redis overrides."""
    from glean_api.dependencies import get_redis_pool

    async def override_get_session():
        yield db_session

    async def override_get_redis_pool():
        return mock_redis

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_redis_pool] = override_get_redis_pool

    # Reset mock redis state before each test
    mock_redis.enqueued_jobs.clear()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def test_mock_redis():
    """Provide access to the mock redis instance for testing."""
    return mock_redis


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    from glean_core.schemas.user import UserCreate
    from glean_core.services.user_service import UserService

    service = UserService(db_session)
    user_create = UserCreate(email="test@example.com", name="Test User", password="TestPass123")
    user = await service.create_user(user_create)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers(test_user: User) -> dict[str, str]:
    """Generate auth headers for test user."""
    from glean_api.config import settings
    from glean_core.auth.jwt import JWTConfig, create_access_token

    jwt_config = JWTConfig(
        secret_key=settings.secret_key,
        algorithm=settings.jwt_algorithm,
        access_token_expire_minutes=settings.jwt_access_token_expire_minutes,
        refresh_token_expire_days=settings.jwt_refresh_token_expire_days,
    )
    access_token = create_access_token(str(test_user.id), jwt_config)
    return {"Authorization": f"Bearer {access_token}"}


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession):
    """Create a test admin user."""
    from glean_core.services import AdminService
    from glean_database.models.admin import AdminRole

    service = AdminService(db_session)
    admin = await service.create_admin_user(
        username="admin_test", password="Admin123!", role=AdminRole.SUPER_ADMIN
    )
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest_asyncio.fixture
async def admin_headers(admin_user: User) -> dict[str, str]:
    """Generate auth headers for admin user."""
    from glean_api.config import settings
    from glean_core.auth.jwt import JWTConfig, create_access_token

    jwt_config = JWTConfig(
        secret_key=settings.secret_key,
        algorithm=settings.jwt_algorithm,
        access_token_expire_minutes=settings.jwt_access_token_expire_minutes,
        refresh_token_expire_days=settings.jwt_refresh_token_expire_days,
    )

    access_token = create_access_token(str(admin_user.id), jwt_config, "admin")
    return {"Authorization": f"Bearer {access_token}"}

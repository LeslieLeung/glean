import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def test_subscription(db_session: AsyncSession, test_user, test_feed):
    """Create a test subscription."""
    from glean_database.models.subscription import Subscription

    subscription = Subscription(user_id=test_user.id, feed_id=test_feed.id)
    db_session.add(subscription)
    await db_session.commit()
    await db_session.refresh(subscription)
    return subscription


@pytest_asyncio.fixture
async def test_feed(db_session: AsyncSession):
    """Create a test feed."""
    from glean_database.models.feed import Feed

    feed = Feed(
        url="https://example.com/feed.xml",
        title="Test Feed",
        description="A test RSS feed",
        status="active",
    )
    db_session.add(feed)
    await db_session.commit()
    await db_session.refresh(feed)
    return feed


@pytest_asyncio.fixture(autouse=True)
async def init_test_database(test_engine):
    """Initialize database for MCP tools tests that use get_session_context()."""
    from glean_database.session import init_database

    # Get test database URL
    test_database_url = os.getenv(
        "TEST_DATABASE_URL",
        os.getenv(
            "DATABASE_URL", "postgresql+asyncpg://glean:devpassword@localhost:5433/glean_test"
        ),
    )

    # Initialize database module with test database URL
    init_database(test_database_url)

    yield


@pytest_asyncio.fixture
async def mcp_db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Create database session for MCP tests that doesn't use transaction rollback.

    This is needed for tests that call MCP tools which create their own sessions
    via get_session_context(). Data committed here will be visible to those sessions.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    async_session = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        # Note: No automatic rollback - tests must clean up their own data
        # or rely on the test_engine fixture's table drop/create cycle

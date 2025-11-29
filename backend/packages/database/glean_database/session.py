"""
Database session management.

This module provides utilities for initializing database connections
and managing async database sessions.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Module-level engine and session factory
_engine = None
_async_session_maker = None


def init_database(database_url: str) -> None:
    """
    Initialize database connection pool.

    Args:
        database_url: PostgreSQL connection URL with asyncpg driver.

    Note:
        This function should be called once at application startup.
    """
    global _engine, _async_session_maker

    _engine = create_async_engine(
        database_url,
        echo=False,
        pool_size=20,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
    )

    _async_session_maker = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get an async database session.

    Yields:
        AsyncSession instance with automatic commit/rollback handling.

    Raises:
        RuntimeError: If database has not been initialized.
    """
    if _async_session_maker is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")

    async with _async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

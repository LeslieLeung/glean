"""
Glean API - FastAPI application entry point.

This module initializes the FastAPI application and configures
middleware, routers, and lifecycle events.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from glean_core import get_logger, init_logging

from .config import settings
from .middleware import LoggingMiddleware
from .routers import admin, auth, bookmarks, entries, feeds, folders, preference, system, tags

# Initialize logging system
init_logging()

# Get logger instance
logger = get_logger(__name__)

# Global Redis connection pool for task queue
redis_pool: ArqRedis | None = None


async def get_redis_pool() -> ArqRedis:
    """
    Get the global Redis connection pool for arq.

    Returns:
        ArqRedis connection pool.

    Raises:
        RuntimeError: If Redis pool not initialized.
    """
    if redis_pool is None:
        raise RuntimeError("Redis pool not initialized")
    return redis_pool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifecycle manager.

    Handles startup and shutdown events for the application.

    Args:
        app: The FastAPI application instance.

    Yields:
        None during application runtime.
    """
    # Startup: Initialize resources
    from glean_database.session import init_database

    global redis_pool

    logger.info(f"Starting Glean API v{settings.version}")
    init_database(settings.database_url)

    # Initialize Redis pool for task queue
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    redis_pool = await create_pool(redis_settings)
    logger.info("Redis pool initialized")

    yield

    # Shutdown: Cleanup resources
    if redis_pool:
        await redis_pool.close()
        logger.info("Redis pool closed")
    logger.info("Shutting down Glean API")


app = FastAPI(
    title="Glean API",
    description="Glean - Personal Knowledge Management Tool API",
    version=settings.version,
    lifespan=lifespan,
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging middleware
app.add_middleware(LoggingMiddleware)

# Register API routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(feeds.router, prefix="/api/feeds", tags=["Feeds"])
app.include_router(entries.router, prefix="/api/entries", tags=["Entries"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(bookmarks.router, prefix="/api/bookmarks", tags=["Bookmarks"])
app.include_router(folders.router, prefix="/api/folders", tags=["Folders"])
app.include_router(tags.router, prefix="/api/tags", tags=["Tags"])
app.include_router(preference.router, prefix="/api/preference", tags=["Preference"])
app.include_router(system.router, prefix="/api/system", tags=["System"])


@app.get("/api/health")
async def health_check() -> dict[str, str]:
    """
    Health check endpoint.

    Returns:
        Dictionary containing service status and version.
    """
    return {"status": "healthy", "version": settings.version}

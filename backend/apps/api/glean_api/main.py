"""
Glean API - FastAPI application entry point.

This module initializes the FastAPI application and configures
middleware, routers, and lifecycle events.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import admin, auth, entries, feeds


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
    print(f"Starting Glean API v{settings.version}")
    yield
    # Shutdown: Cleanup resources
    print("Shutting down Glean API")


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

# Register API routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(feeds.router, prefix="/api/feeds", tags=["Feeds"])
app.include_router(entries.router, prefix="/api/entries", tags=["Entries"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])


@app.get("/api/health")
async def health_check() -> dict[str, str]:
    """
    Health check endpoint.

    Returns:
        Dictionary containing service status and version.
    """
    return {"status": "healthy", "version": settings.version}

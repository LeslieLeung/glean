"""
Glean API - FastAPI application entry point.

This module initializes the FastAPI application and configures
middleware, routers, and lifecycle events.

Provides a ``create_app()`` factory function that can be called by
extension layers (e.g. SaaS) to create a customised application
instance with additional routers, middleware and lifecycle hooks.
"""

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from enum import Enum
from typing import Any, cast

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware

from glean_core import get_logger, init_logging
from glean_vector.config import (
    embedding_model_fingerprint,
    vector_backend_config,
    vector_store_fingerprint,
)

from .config import settings
from .mcp import create_mcp_server
from .middleware import LoggingMiddleware
from .routers import (
    admin,
    api_tokens,
    auth,
    bookmarks,
    entries,
    feeds,
    folders,
    preference,
    system,
    tags,
)
from .vector_lifecycle import (
    ensure_app_vector_client,
    initialize_vector_client_state,
    reconcile_vector_backend,
)

# Initialize logging system
init_logging()

# Get logger instance
logger = get_logger(__name__)

RouterTags = list[str | Enum]
RouterConfig = tuple[APIRouter, str, RouterTags]
MiddlewareConfig = tuple[type[Any], dict[str, Any]]


async def get_redis_pool(request: Request) -> ArqRedis:
    """
    Get the app-scoped Redis connection pool for arq.

    Returns:
        ArqRedis connection pool.

    Raises:
        RuntimeError: If Redis pool not initialized.
    """
    redis_pool = getattr(request.app.state, "redis_pool", None)
    if redis_pool is None:
        raise RuntimeError("Redis pool not initialized")
    return redis_pool


def get_oss_routers() -> list[RouterConfig]:
    """Return all OSS routers as (router, prefix, tags) tuples."""
    return [
        (auth.router, "/api/auth", ["Authentication"]),
        (feeds.router, "/api/feeds", ["Feeds"]),
        (entries.router, "/api/entries", ["Entries"]),
        (admin.router, "/api/admin", ["Admin"]),
        (bookmarks.router, "/api/bookmarks", ["Bookmarks"]),
        (folders.router, "/api/folders", ["Folders"]),
        (tags.router, "/api/tags", ["Tags"]),
        (preference.router, "/api/preference", ["Preference"]),
        (system.router, "/api/system", ["System"]),
        (api_tokens.router, "/api/tokens", ["API Tokens"]),
    ]


def create_app(
    extra_routers: list[RouterConfig] | None = None,
    extra_startup: Callable[[], Awaitable[None]] | None = None,
    extra_shutdown: Callable[[], Awaitable[None]] | None = None,
    extra_middleware: list[MiddlewareConfig] | None = None,
) -> FastAPI:
    """
    Composable App factory.

    Extensions (e.g. SaaS layer) inject additional routers,
    middleware and lifecycle hooks via parameters.

    Args:
        extra_routers: Additional (router, prefix, tags) to register.
        extra_startup: Async callable invoked during startup.
        extra_shutdown: Async callable invoked during shutdown.
        extra_middleware: Additional (middleware_class, kwargs) to add.

    Returns:
        Configured FastAPI application.
    """
    # Intentionally create one MCP server per FastAPI app instance to keep
    # lifecycle/session-manager state isolated between factory-created apps.
    mcp_server = create_mcp_server()
    mcp_http_app = mcp_server.streamable_http_app()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
        from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus
        from glean_core.services import TypedConfigService
        from glean_database.session import get_session_context, init_database

        logger.info(f"Starting Glean API v{settings.version}")
        init_database(settings.database_url)

        # Initialize Redis pool for task queue
        redis_settings = RedisSettings.from_dsn(settings.redis_url)
        _app.state.redis_pool = await create_pool(redis_settings)
        logger.info("Redis pool initialized")

        initialize_vector_client_state(_app)
        try:
            async with get_session_context() as session:
                config_service = TypedConfigService(session)
                config = await reconcile_vector_backend(_app, session)

                if config.enabled and config.status == VectorizationStatus.IDLE:
                    vector_client, vector_error = await ensure_app_vector_client(
                        _app,
                        config.dimension,
                        config.provider,
                        config.model,
                    )
                    if vector_client is None:
                        raise RuntimeError(vector_error or "Vector backend unavailable")

                    # Empty pgvector installations and legacy Milvus stores are
                    # safe to adopt only after schema/model compatibility has
                    # actually been verified.
                    if (
                        config.vector_backend is None
                        or config.vector_store_fingerprint is None
                        or config.model_fingerprint is None
                    ):
                        adopted = await config_service.update_embedding_generation(
                            expected_version=config.version,
                            expected_rebuild_id=config.rebuild_id,
                            expected_statuses={VectorizationStatus.IDLE.value},
                            expected_values={
                                "enabled": config.enabled,
                                "provider": config.provider,
                                "model": config.model,
                                "dimension": config.dimension,
                                "base_url": config.base_url,
                            },
                            vector_backend=vector_backend_config.backend.lower(),
                            vector_store_fingerprint=vector_store_fingerprint(),
                            model_fingerprint=embedding_model_fingerprint(
                                config.provider,
                                config.model,
                                config.dimension,
                                config.base_url,
                            ),
                            target_vector_backend=None,
                            target_vector_store_fingerprint=None,
                            target_model_fingerprint=None,
                            target_force_rebuild=False,
                        )
                        if adopted is not None:
                            config = adopted
                        else:
                            config = await config_service.get(EmbeddingConfig)

            if config.enabled and config.status == VectorizationStatus.IDLE:
                logger.info(
                    "Vector client initialized",
                    extra={"backend": vector_backend_config.backend},
                )
        except Exception as e:
            _app.state.vector_client = None
            _app.state.vector_client_error = str(e)
            logger.warning(
                "Vector client unavailable for API scoring",
                extra={"backend": vector_backend_config.backend, "error": str(e)},
            )

        # Run extra startup hook
        if extra_startup:
            await extra_startup()

        # Initialize MCP server session manager
        async with mcp_server.session_manager.run():
            logger.info("MCP server initialized")
            yield

        # Shutdown: Cleanup resources
        try:
            if extra_shutdown:
                await extra_shutdown()
        finally:
            vector_client = getattr(_app.state, "vector_client", None)
            if vector_client:
                await vector_client.disconnect()
                _app.state.vector_client = None
                logger.info(
                    "Vector client disconnected",
                    extra={"backend": vector_backend_config.backend},
                )
            redis_pool = getattr(_app.state, "redis_pool", None)
            if redis_pool:
                await redis_pool.close()
                _app.state.redis_pool = None
                logger.info("Redis pool closed")
            logger.info("Shutting down Glean API")

    application = FastAPI(
        title="Glean API",
        description="Glean - Personal Knowledge Management Tool API",
        version=settings.version,
        lifespan=lifespan,
        docs_url="/api/docs" if settings.debug else None,
        redoc_url="/api/redoc" if settings.debug else None,
    )

    # Configure CORS middleware
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Configure logging middleware
    application.add_middleware(LoggingMiddleware)

    # Register extra middleware
    if extra_middleware:
        for middleware_cls, kwargs in extra_middleware:
            application.add_middleware(cast(Any, middleware_cls), **kwargs)

    # Register OSS routers
    for router, prefix, router_tags in get_oss_routers():
        application.include_router(router, prefix=prefix, tags=router_tags)

    # Register extra routers
    if extra_routers:
        for router, prefix, router_tags in extra_routers:
            application.include_router(router, prefix=prefix, tags=router_tags)

    # Mount MCP server
    application.mount("/mcp", mcp_http_app)

    application.add_api_route("/api/health", health_check, methods=["GET"])

    return application


async def health_check(request: Request) -> dict[str, str]:
    """Readiness check, including the active vector backend when enabled."""
    from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus
    from glean_core.services import TypedConfigService
    from glean_database.session import get_session_context
    from glean_vector.config import is_active_embedding_model, is_active_vector_backend

    try:
        async with get_session_context() as session:
            config_service = TypedConfigService(session)
            config = await config_service.get(EmbeddingConfig)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unavailable: {exc}",
        ) from exc

    # VALIDATING/REBUILDING may intentionally point at a not-yet-recreated
    # store. Keep the API ready so the worker can perform that rebuild; IDLE is
    # the state that promises a usable active backend.
    if config.enabled and config.status == VectorizationStatus.IDLE:
        if not is_active_vector_backend(
            config.vector_backend,
            config.vector_store_fingerprint,
        ) or not is_active_embedding_model(
            config.model_fingerprint,
            provider=config.provider,
            model=config.model,
            dimension=config.dimension,
            base_url=config.base_url,
        ):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Vector backend transition is pending: "
                    f"stored={config.vector_backend or 'unknown'}, "
                    f"runtime={vector_backend_config.backend}"
                ),
            )
        vector_client, vector_error = await ensure_app_vector_client(
            request.app,
            config.dimension,
            config.provider,
            config.model,
        )
        if vector_client is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Vector backend unavailable: {vector_error or 'unknown error'}",
            )

    return {"status": "healthy", "version": settings.version}


# Backward compatible: OSS mode uses the factory directly
app = create_app()

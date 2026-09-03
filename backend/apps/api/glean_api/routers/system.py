"""
System router.

Provides public endpoints for system information and status.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core.schemas.config import (
    EmbeddingConfig,
    EmbeddingRebuildProgress,
    VectorizationStatus,
    VectorizationStatusResponse,
)
from glean_core.services import TypedConfigService
from glean_database.models import Entry
from glean_database.session import get_session
from glean_vector.config import (
    is_active_embedding_model,
    is_active_vector_backend,
    vector_backend_config,
)

from ..vector_lifecycle import ensure_app_vector_client

router = APIRouter()


async def get_config_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TypedConfigService:
    """Get typed config service instance."""
    return TypedConfigService(session)


@router.get("/vectorization-status", response_model=VectorizationStatusResponse)
async def get_vectorization_status(
    request: Request,
    config_service: Annotated[TypedConfigService, Depends(get_config_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> VectorizationStatusResponse:
    """
    Get vectorization system status.

    This is a public endpoint (requires authentication) for the frontend
    to determine if vectorization features are available.

    Returns:
        Vectorization status including enabled state and any errors.
    """
    config = await config_service.get(EmbeddingConfig)

    # Build progress info if rebuilding
    progress = None
    current_status = config.status

    if config.status == VectorizationStatus.REBUILDING:
        result = await session.execute(
            select(Entry.embedding_status, func.count())
            .where(Entry.embedding_status.in_(["pending", "processing", "done", "failed"]))
            .group_by(Entry.embedding_status)
        )
        counts: dict[str, int] = {str(row[0]): int(row[1]) for row in result.all()}

        pending = counts.get("pending", 0)
        processing = counts.get("processing", 0)
        done = counts.get("done", 0)
        failed = counts.get("failed", 0)

        progress = EmbeddingRebuildProgress(
            total=pending + processing + done + failed,
            pending=pending,
            processing=processing,
            done=done,
            failed=failed,
        )

    runtime_error = getattr(request.app.state, "vector_client_error", None)
    backend_current = is_active_vector_backend(
        config.vector_backend,
        config.vector_store_fingerprint,
    ) and is_active_embedding_model(
        config.model_fingerprint,
        provider=config.provider,
        model=config.model,
        dimension=config.dimension,
        base_url=config.base_url,
    )
    if config.enabled and current_status == VectorizationStatus.IDLE and not backend_current:
        runtime_error = (
            "Vector backend transition is pending: "
            f"stored={config.vector_backend or 'unknown'}, "
            f"runtime={vector_backend_config.backend}"
        )
    if config.enabled and current_status == VectorizationStatus.IDLE and backend_current:
        _client, runtime_error = await ensure_app_vector_client(
            request.app,
            config.dimension,
            config.provider,
            config.model,
        )

    if config.enabled and runtime_error and current_status == VectorizationStatus.IDLE:
        current_status = VectorizationStatus.ERROR

    return VectorizationStatusResponse(
        enabled=config.enabled,
        status=current_status,
        has_error=current_status == VectorizationStatus.ERROR,
        error_message=(runtime_error or config.last_error)
        if current_status == VectorizationStatus.ERROR
        else None,
        rebuild_progress=progress,
    )


@router.get("/health")
async def health_check() -> dict[str, str]:
    """
    Basic health check endpoint.

    Returns:
        Health status.
    """
    return {"status": "healthy"}

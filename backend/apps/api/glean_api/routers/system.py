"""
System router.

Provides public endpoints for system information and status.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
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

router = APIRouter()


async def get_config_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TypedConfigService:
    """Get typed config service instance."""
    return TypedConfigService(session)


@router.get("/vectorization-status", response_model=VectorizationStatusResponse)
async def get_vectorization_status(
    config_service: Annotated[TypedConfigService, Depends(get_config_service)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> VectorizationStatusResponse:
    """
    Get vectorization system status.

    This is a public endpoint (requires authentication) for the frontend
    to determine if vectorization features are available.

    If status is REBUILDING and all entries are processed, automatically
    updates status to IDLE.

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

        # Auto-complete rebuild when no entries remain in a non-terminal state.
        # This also covers an empty instance (no entries at all), which would
        # otherwise stay stuck in REBUILDING since done + failed never grows.
        if pending == 0 and processing == 0:
            await config_service.complete_rebuild()
            current_status = VectorizationStatus.IDLE

    return VectorizationStatusResponse(
        enabled=config.enabled,
        status=current_status,
        has_error=current_status == VectorizationStatus.ERROR,
        error_message=config.last_error if current_status == VectorizationStatus.ERROR else None,
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

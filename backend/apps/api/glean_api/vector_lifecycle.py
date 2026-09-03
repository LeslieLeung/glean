"""Application-scoped vector client lifecycle helpers."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core import get_logger
from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus
from glean_core.services import TypedConfigService
from glean_database.models import Entry
from glean_vector.clients import create_vector_store_client
from glean_vector.clients.vector_store import VectorStoreClient
from glean_vector.config import (
    embedding_model_fingerprint,
    vector_backend_config,
    vector_store_fingerprint,
)

logger = get_logger(__name__)


def initialize_vector_client_state(app: Any) -> None:
    """Initialize vector client state for a FastAPI application."""
    app.state.vector_client = None
    app.state.vector_client_error = None
    app.state.vector_client_lock = asyncio.Lock()


async def reconcile_vector_backend(
    app: Any,
    session: AsyncSession,
) -> EmbeddingConfig:
    """Fence deployment backend changes before any API vector access.

    ``VECTOR_BACKEND`` is deployment configuration while embedding settings
    live in PostgreSQL.  When they disagree, start a new validation generation
    before a request can accidentally provision or query the newly selected,
    still-empty backend.
    """
    config_service = TypedConfigService(session)
    config = await config_service.get(EmbeddingConfig)
    if not config.enabled:
        return config

    runtime_backend = vector_backend_config.backend.lower()
    runtime_store_fingerprint = vector_store_fingerprint()
    runtime_model_fingerprint = embedding_model_fingerprint(
        config.provider,
        config.model,
        config.dimension,
        config.base_url,
    )
    backend_changed = (
        config.vector_backend is not None and config.vector_backend.lower() != runtime_backend
    )
    backend_changed = backend_changed or (
        config.vector_store_fingerprint is not None
        and config.vector_store_fingerprint != runtime_store_fingerprint
    )
    backend_changed = backend_changed or (
        config.model_fingerprint is not None
        and config.model_fingerprint != runtime_model_fingerprint
    )
    entry_count = 0
    if config.vector_backend is None and runtime_backend == "pgvector":
        entry_count = await session.scalar(select(func.count()).select_from(Entry))
        backend_changed = int(entry_count or 0) > 0

    # Before ensure_collections can provision an empty store, inspect the
    # existing backend read-only. A connection failure is also a transition:
    # leaving the config IDLE could let a later ensure silently create an
    # empty store after the backend recovers.
    if config.status == VectorizationStatus.IDLE and not backend_changed:
        from glean_vector.services import EmbeddingValidationService

        done_entry_count = int(
            await session.scalar(
                select(func.count()).select_from(Entry).where(Entry.embedding_status == "done")
            )
            or 0
        )
        backend_result = await EmbeddingValidationService().validate_vector_backend(
            config.dimension,
            config.provider,
            config.model,
        )
        if not backend_result.success:
            backend_changed = True
        else:
            details = backend_result.details
            if not bool(details.get("collections_exist")) or not bool(details.get("is_compatible")):
                backend_changed = True
            backend_entry_count = details.get("entry_vector_count")
            if backend_entry_count is not None and int(backend_entry_count) < done_entry_count:
                backend_changed = True

    should_resume_validation = config.status == VectorizationStatus.VALIDATING
    if not backend_changed and not should_resume_validation:
        return config

    if should_resume_validation:
        target_is_complete = all(
            (
                config.target_vector_backend,
                config.target_vector_store_fingerprint,
                config.target_model_fingerprint,
            )
        )
        if target_is_complete and (
            config.target_vector_backend != runtime_backend
            or config.target_vector_store_fingerprint != runtime_store_fingerprint
            or config.target_model_fingerprint != runtime_model_fingerprint
        ):
            # Another deployment generation owns this transition. An older
            # replica must neither validate nor overwrite its desired target.
            logger.info(
                "Skipping vector reconciliation for a different target deployment",
                extra={
                    "target_backend": config.target_vector_backend,
                    "runtime_backend": runtime_backend,
                    "version": config.version,
                },
            )
            return config

    version = config.version
    if (backend_changed and not should_resume_validation) or version is None:
        version = str(uuid4())
        updated = await config_service.update_embedding_generation(
            expected_version=config.version,
            expected_rebuild_id=config.rebuild_id,
            expected_statuses={config.status.value},
            expected_values={
                "enabled": config.enabled,
                "provider": config.provider,
                "model": config.model,
                "dimension": config.dimension,
                "base_url": config.base_url,
            },
            version=version,
            status=VectorizationStatus.VALIDATING,
            target_vector_backend=runtime_backend,
            target_vector_store_fingerprint=runtime_store_fingerprint,
            target_model_fingerprint=runtime_model_fingerprint,
            target_force_rebuild=False,
            rebuild_id=None,
            rebuild_started_at=None,
            rebuild_phase=None,
            last_error=None,
            last_error_at=None,
            error_count=0,
        )
        if updated is None:
            # A concurrent admin/startup transition won. Its owner is
            # responsible for enqueueing; never overwrite that generation.
            return await config_service.get(EmbeddingConfig)
        config = updated
    elif not all(
        (
            config.target_vector_backend,
            config.target_vector_store_fingerprint,
            config.target_model_fingerprint,
        )
    ):
        # Backfill a validation generation created by an earlier release.
        updated = await config_service.update_embedding_generation(
            expected_version=config.version,
            expected_rebuild_id=config.rebuild_id,
            expected_statuses={config.status.value},
            target_vector_backend=runtime_backend,
            target_vector_store_fingerprint=runtime_store_fingerprint,
            target_model_fingerprint=runtime_model_fingerprint,
            target_force_rebuild=False,
        )
        if updated is None:
            return await config_service.get(EmbeddingConfig)
        config = updated

    redis = getattr(app.state, "redis_pool", None)
    if redis is None:
        raise RuntimeError("Redis pool unavailable for vector backend reconciliation")
    await redis.enqueue_job(
        "validate_and_rebuild_embeddings",
        expected_version=version,
        expected_backend=config.target_vector_backend,
        expected_store_fingerprint=config.target_vector_store_fingerprint,
        expected_model_fingerprint=config.target_model_fingerprint,
        _job_id=f"validate_embedding_{version}",
    )
    logger.info(
        "Embedding validation queued during API startup",
        extra={
            "stored_backend": config.vector_backend,
            "runtime_backend": runtime_backend,
            "backend_changed": backend_changed,
            "version": version,
        },
    )
    return config


async def ensure_app_vector_client(
    app: Any,
    dimension: int,
    provider: str,
    model: str,
) -> tuple[VectorStoreClient | None, str | None]:
    """Return a ready app-scoped vector client, recovering it on demand.

    API startup is deliberately tolerant of a temporarily unavailable vector
    backend.  Every enabled vector feature goes through this helper so the
    process can recover without a restart once the backend becomes available.
    """
    lock = getattr(app.state, "vector_client_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        app.state.vector_client_lock = lock

    async with lock:
        client = getattr(app.state, "vector_client", None)
        try:
            if client is None:
                client = create_vector_store_client()
                client.connect()

            await client.ensure_collections(dimension, provider, model)
        except Exception as exc:
            if client is not None:
                with contextlib.suppress(Exception):
                    await client.disconnect()
            error = str(exc)
            app.state.vector_client = None
            app.state.vector_client_error = error
            logger.warning(
                "Vector client unavailable",
                extra={"backend": vector_backend_config.backend, "error": error},
            )
            return None, error

        app.state.vector_client = client
        app.state.vector_client_error = None
        return client, None

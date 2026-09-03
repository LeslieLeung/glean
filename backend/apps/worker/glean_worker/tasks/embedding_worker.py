"""Embedding generation worker tasks."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from arq import Retry
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core import get_logger
from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus
from glean_core.services import TypedConfigService
from glean_database.models import Entry
from glean_database.session import get_session_context
from glean_vector.clients.embedding_client import EmbeddingClient
from glean_vector.config import EmbeddingConfig as EmbeddingSettings
from glean_vector.config import (
    embedding_model_fingerprint,
    is_active_embedding_model,
    is_active_vector_backend,
    vector_backend_config,
    vector_store_fingerprint,
)
from glean_vector.services.embedding_service import (
    EmbeddingService,
    StaleEmbeddingGenerationError,
)

from ._vector_client import ensure_vector_client

logger = get_logger(__name__)

# Circuit breaker state
CONSECUTIVE_FAILURES_THRESHOLD = 5


async def _check_vectorization_enabled(session: AsyncSession) -> tuple[bool, EmbeddingConfig]:
    """
    Check if vectorization is enabled and healthy.

    Returns:
        Tuple of (is_enabled, config)
    """
    config_service = TypedConfigService(session)
    config = await config_service.get(EmbeddingConfig)

    # Check if enabled and in a working state
    is_enabled = (
        config.enabled
        and is_active_vector_backend(
            config.vector_backend,
            config.vector_store_fingerprint,
        )
        and is_active_embedding_model(
            config.model_fingerprint,
            provider=config.provider,
            model=config.model,
            dimension=config.dimension,
            base_url=config.base_url,
        )
        and config.status
        in (
            VectorizationStatus.IDLE,
            VectorizationStatus.REBUILDING,
        )
    )

    return is_enabled, config


async def _load_embedding_settings(config: EmbeddingConfig) -> tuple[EmbeddingSettings, int]:
    """
    Build embedding settings from typed config.

    Returns:
        Tuple of (EmbeddingSettings, rate_limit)
    """
    settings = EmbeddingSettings(
        provider=config.provider,
        model=config.model,
        dimension=config.dimension,
        api_key=config.api_key or "",
        base_url=config.base_url,
        timeout=config.timeout,
        batch_size=config.batch_size,
        max_retries=config.max_retries,
    )
    rate_limit = config.get_rate_limit_for_provider()
    return settings, rate_limit


def _generation_guard(
    session: AsyncSession,
    *,
    expected_version: str | None,
    expected_rebuild_id: str | None,
) -> Callable[[], Awaitable[bool]]:
    """Build a config-generation check used immediately before vector writes."""

    async def check() -> bool:
        # Avoid reusing a cached SystemConfig row in a long-running batch.
        session.expire_all()
        current = await TypedConfigService(session).get(EmbeddingConfig)
        if current.version != expected_version:
            return False
        if expected_rebuild_id is not None:
            return (
                current.status == VectorizationStatus.REBUILDING
                and current.rebuild_id == expected_rebuild_id
            )
        return current.status in (
            VectorizationStatus.IDLE,
            VectorizationStatus.REBUILDING,
        )

    return check


async def _handle_embedding_error(
    session: AsyncSession,
    error: Exception,
    *,
    expected_version: str | None,
    expected_rebuild_id: str | None,
) -> int | None:
    """
    Handle embedding error with circuit breaker logic.

    After CONSECUTIVE_FAILURES_THRESHOLD failures, sets status to ERROR.
    """
    result = await TypedConfigService(session).record_embedding_failure(
        expected_version=expected_version,
        expected_rebuild_id=expected_rebuild_id,
        error=error,
        circuit_threshold=CONSECUTIVE_FAILURES_THRESHOLD,
    )
    if result is None:
        return None
    new_error_count, circuit_open = result
    if circuit_open:
        logger.warning(f"Circuit breaker triggered after {new_error_count} consecutive failures")
    return new_error_count


async def _reset_error_count(
    session: AsyncSession,
    *,
    expected_version: str | None,
    expected_rebuild_id: str | None,
) -> None:
    """Reset error count only on the generation that succeeded."""
    await TypedConfigService(session).reset_embedding_errors(
        expected_version=expected_version,
        expected_rebuild_id=expected_rebuild_id,
    )


async def _safe_handle_error(
    session: AsyncSession,
    error: Exception,
    *,
    expected_version: str | None,
    expected_rebuild_id: str | None,
) -> int | None:
    """Handle embedding error, recovering from a poisoned session first.

    When a prior DB operation fails, asyncpg puts the connection into a
    failed-transaction state.  This helper rolls back before touching the
    session so the circuit-breaker logic can still read/write config.
    """
    import contextlib

    with contextlib.suppress(Exception):
        await session.rollback()
    try:
        failure_count = await _handle_embedding_error(
            session,
            error,
            expected_version=expected_version,
            expected_rebuild_id=expected_rebuild_id,
        )
        # generate_entry_embedding may raise arq.Retry below.  Commit the
        # circuit-breaker update before that exception leaves the session
        # context, otherwise its automatic rollback would lose the count.
        await session.commit()
        return failure_count
    except Exception:
        logger.warning("Could not update circuit breaker after error", exc_info=True)
        with contextlib.suppress(Exception):
            await session.rollback()
        return None


def _embedding_job_try(ctx: dict[str, Any]) -> int:
    """Return the current arq attempt number with a safe default."""
    try:
        return max(1, int(ctx.get("job_try", 1)))
    except (TypeError, ValueError):
        return 1


def _embedding_retry_delay(ctx: dict[str, Any]) -> timedelta:
    """Return a bounded exponential delay for a single-entry retry."""
    job_try = _embedding_job_try(ctx)
    return timedelta(seconds=min(60 * (2 ** (job_try - 1)), 15 * 60))


async def generate_entry_embedding(ctx: dict[str, Any], entry_id: str) -> dict[str, Any]:
    """
    Generate embedding for a single entry.

    Args:
        ctx: Worker context
        entry_id: Entry UUID

    Returns:
        Result dictionary
    """
    vector_client, vector_error = ensure_vector_client(ctx)
    if not vector_client:
        error = "Vector backend unavailable"
        if vector_error:
            error = f"{error}: {vector_error}"
        # Connection creation failed before a DB service could record the
        # entry failure.  Let arq retry with bounded backoff so a transient
        # backend outage can recover without a tight retry loop.
        if _embedding_job_try(ctx) < CONSECUTIVE_FAILURES_THRESHOLD:
            raise Retry(defer=_embedding_retry_delay(ctx))
        return {"success": False, "entry_id": entry_id, "error": error}

    async with get_session_context() as session:
        # Check if vectorization is enabled
        is_enabled, config = await _check_vectorization_enabled(session)
        if not is_enabled:
            logger.debug(f"Vectorization disabled, skipping embedding for {entry_id}")
            return {"success": False, "entry_id": entry_id, "error": "Vectorization disabled"}

        settings, rate_limit = await _load_embedding_settings(config)
        embedding_client = EmbeddingClient(config=settings, rate_limit=rate_limit)
        embedding_service: EmbeddingService | None = None

        try:
            # Ensure vector storage exists with correct model config
            await vector_client.ensure_collections(
                settings.dimension, settings.provider, settings.model
            )

            embedding_service = EmbeddingService(
                db_session=session,
                embedding_client=embedding_client,
                vector_client=vector_client,
                generation_guard=_generation_guard(
                    session,
                    expected_version=config.version,
                    expected_rebuild_id=config.rebuild_id,
                ),
                generation_lock=ctx.get("redis"),
            )

            success = await embedding_service.generate_embedding(entry_id)

            if success:
                await _reset_error_count(
                    session,
                    expected_version=config.version,
                    expected_rebuild_id=config.rebuild_id,
                )

            return {"success": success, "entry_id": entry_id}

        except StaleEmbeddingGenerationError:
            await session.rollback()
            if embedding_service is not None:
                await embedding_service.restore_claimed_entries([entry_id])
            return {
                "success": False,
                "entry_id": entry_id,
                "skipped": "Stale embedding generation",
            }
        except Exception as e:
            # Infrastructure errors are persisted as "failed" by the service
            # layer.  Count the failure durably and ask arq for a bounded,
            # deferred retry while the circuit is still closed.
            error_msg = str(e)
            logger.error(
                f"Failed to generate embedding for entry {entry_id}: {error_msg}",
                exc_info=True,
            )
            failure_count = await _safe_handle_error(
                session,
                e,
                expected_version=config.version,
                expected_rebuild_id=config.rebuild_id,
            )
            job_try = _embedding_job_try(ctx)
            circuit_open = (
                failure_count is not None and failure_count >= CONSECUTIVE_FAILURES_THRESHOLD
            )
            if not circuit_open and job_try < CONSECUTIVE_FAILURES_THRESHOLD:
                raise Retry(defer=_embedding_retry_delay(ctx)) from e
            return {"success": False, "entry_id": entry_id, "error": error_msg}

        finally:
            await embedding_client.close()


async def batch_generate_embeddings(
    ctx: dict[str, Any],
    limit: int = 100,
    rebuild_id: str | None = None,
    expected_backend: str | None = None,
    expected_store_fingerprint: str | None = None,
    expected_model_fingerprint: str | None = None,
) -> dict[str, int | str]:
    """
    Batch generate embeddings for pending entries.

    Args:
        ctx: Worker context
        limit: Maximum number of entries to process

    Returns:
        Result dictionary with processed and failed counts
    """
    if (
        expected_backend is not None
        and expected_backend.lower() != vector_backend_config.backend.lower()
    ):
        raise Retry(defer=timedelta(seconds=15))
    if (
        expected_store_fingerprint is not None
        and expected_store_fingerprint != vector_store_fingerprint()
    ):
        raise Retry(defer=timedelta(seconds=15))

    vector_client, vector_error = ensure_vector_client(ctx)
    if not vector_client:
        error = "Vector backend unavailable"
        if vector_error:
            error = f"{error}: {vector_error}"
        return {"processed": 0, "failed": 0, "error": error}

    async with get_session_context() as session:
        # Check if vectorization is enabled
        is_enabled, config = await _check_vectorization_enabled(session)
        if not is_enabled:
            logger.debug("Vectorization disabled, skipping batch generate")
            return {"processed": 0, "failed": 0, "skipped": "Vectorization disabled"}
        if rebuild_id is not None and (
            config.status != VectorizationStatus.REBUILDING or config.rebuild_id != rebuild_id
        ):
            logger.info(
                "Skipping stale embedding batch",
                extra={"job_rebuild_id": rebuild_id, "current_rebuild_id": config.rebuild_id},
            )
            return {"processed": 0, "failed": 0, "skipped": "Stale rebuild job"}
        if expected_model_fingerprint is not None and expected_model_fingerprint != (
            embedding_model_fingerprint(
                config.provider,
                config.model,
                config.dimension,
                config.base_url,
            )
        ):
            return {"processed": 0, "failed": 0, "skipped": "Stale embedding model"}

        settings, rate_limit = await _load_embedding_settings(config)
        embedding_client = EmbeddingClient(config=settings, rate_limit=rate_limit)

        try:
            # Ensure vector storage exists with correct model config
            await vector_client.ensure_collections(
                settings.dimension, settings.provider, settings.model
            )

            embedding_service = EmbeddingService(
                db_session=session,
                embedding_client=embedding_client,
                vector_client=vector_client,
                generation_guard=_generation_guard(
                    session,
                    expected_version=config.version,
                    expected_rebuild_id=rebuild_id,
                ),
                generation_lock=ctx.get("redis"),
            )

            result = await embedding_service.batch_generate(limit=limit)

            processed = result.get("processed", 0)
            failed = result.get("failed", 0)

            if processed > 0:
                await _reset_error_count(
                    session,
                    expected_version=config.version,
                    expected_rebuild_id=rebuild_id,
                )
            elif failed > 0:
                # Entire batch failed — count toward circuit breaker.
                # Session may be dirty; rollback before using it for config.
                await _safe_handle_error(
                    session,
                    RuntimeError(f"Batch: all {failed} entries failed, 0 succeeded"),
                    expected_version=config.version,
                    expected_rebuild_id=rebuild_id,
                )

            return result  # type: ignore[return-value]

        except Exception as e:
            logger.error(f"Failed to batch generate embeddings: {e}")
            await _safe_handle_error(
                session,
                e,
                expected_version=config.version,
                expected_rebuild_id=rebuild_id,
            )
            return {"processed": 0, "failed": 0, "error": str(e)}

        finally:
            await embedding_client.close()


async def retry_failed_embeddings(ctx: dict[str, Any], limit: int = 50) -> dict[str, int | str]:
    """
    Retry failed embeddings.

    Args:
        ctx: Worker context
        limit: Maximum number of entries to retry

    Returns:
        Result dictionary with processed and failed counts
    """
    vector_client, vector_error = ensure_vector_client(ctx)
    if not vector_client:
        error = "Vector backend unavailable"
        if vector_error:
            error = f"{error}: {vector_error}"
        return {"processed": 0, "failed": 0, "error": error}

    async with get_session_context() as session:
        # Check if vectorization is enabled
        is_enabled, config = await _check_vectorization_enabled(session)
        if not is_enabled:
            logger.debug("Vectorization disabled, skipping retry")
            return {"processed": 0, "failed": 0, "skipped": "Vectorization disabled"}

        settings, rate_limit = await _load_embedding_settings(config)
        embedding_client = EmbeddingClient(config=settings, rate_limit=rate_limit)

        try:
            # Ensure vector storage exists with correct model config
            await vector_client.ensure_collections(
                settings.dimension, settings.provider, settings.model
            )

            embedding_service = EmbeddingService(
                db_session=session,
                embedding_client=embedding_client,
                vector_client=vector_client,
                generation_guard=_generation_guard(
                    session,
                    expected_version=config.version,
                    expected_rebuild_id=config.rebuild_id,
                ),
                generation_lock=ctx.get("redis"),
            )

            result = await embedding_service.retry_failed(limit=limit)

            processed = result.get("processed", 0)
            failed = result.get("failed", 0)

            if processed > 0:
                await _reset_error_count(
                    session,
                    expected_version=config.version,
                    expected_rebuild_id=config.rebuild_id,
                )
            elif failed > 0:
                await _safe_handle_error(
                    session,
                    RuntimeError(f"Retry batch: all {failed} entries failed, 0 succeeded"),
                    expected_version=config.version,
                    expected_rebuild_id=config.rebuild_id,
                )

            return result  # type: ignore[return-value]

        except Exception as e:
            logger.error(f"Failed to retry failed embeddings: {e}")
            await _safe_handle_error(
                session,
                e,
                expected_version=config.version,
                expected_rebuild_id=config.rebuild_id,
            )
            return {"processed": 0, "failed": 0, "error": str(e)}

        finally:
            await embedding_client.close()


async def validate_and_rebuild_embeddings(
    ctx: dict[str, Any],
    force_rebuild: bool = False,
    expected_version: str | None = None,
    expected_backend: str | None = None,
    expected_store_fingerprint: str | None = None,
    expected_model_fingerprint: str | None = None,
) -> dict[str, Any]:
    """
    Validate embedding config and trigger rebuild if valid.

    This task is triggered when vectorization is enabled or config is changed.
    When force_rebuild is True (explicit user action), the compatibility check
    is skipped and a full rebuild is always triggered.
    """
    runtime_backend = vector_backend_config.backend.lower()
    runtime_store_fingerprint = vector_store_fingerprint()
    if expected_backend is not None and expected_backend.lower() != runtime_backend:
        logger.info(
            "Validation job reached a worker for another vector backend",
            extra={
                "expected_backend": expected_backend,
                "runtime_backend": vector_backend_config.backend,
            },
        )
        raise Retry(defer=timedelta(seconds=15))
    if (
        expected_store_fingerprint is not None
        and expected_store_fingerprint != runtime_store_fingerprint
    ):
        raise Retry(defer=timedelta(seconds=15))

    redis = ctx.get("redis")

    async with get_session_context() as session:
        config_service = TypedConfigService(session)
        config = await config_service.get(EmbeddingConfig)

        if expected_version is not None and config.version != expected_version:
            logger.info(
                "Skipping stale embedding validation",
                extra={"expected_version": expected_version, "current_version": config.version},
            )
            return {"success": False, "skipped": "stale config version"}

        if not config.enabled:
            return {"success": False, "error": "Vectorization is not enabled"}
        runtime_model_fingerprint = embedding_model_fingerprint(
            config.provider,
            config.model,
            config.dimension,
            config.base_url,
        )

        target_backend = config.target_vector_backend or expected_backend or runtime_backend
        target_store_fingerprint = (
            config.target_vector_store_fingerprint
            or expected_store_fingerprint
            or runtime_store_fingerprint
        )
        target_model_fingerprint = (
            config.target_model_fingerprint
            or expected_model_fingerprint
            or runtime_model_fingerprint
        )
        if (
            (expected_backend is not None and expected_backend.lower() != target_backend.lower())
            or (
                expected_store_fingerprint is not None
                and expected_store_fingerprint != target_store_fingerprint
            )
            or (
                expected_model_fingerprint is not None
                and expected_model_fingerprint != target_model_fingerprint
            )
        ):
            return {"success": False, "skipped": "stale validation target"}

        if (
            target_backend.lower() != runtime_backend
            or target_store_fingerprint != runtime_store_fingerprint
        ):
            # The queue is shared by replicas during rolling deployments.
            # Leave the generation pending for a worker configured for its
            # persisted target instead of touching this replica's store.
            raise Retry(defer=timedelta(seconds=15))
        if target_model_fingerprint != runtime_model_fingerprint:
            return {"success": False, "skipped": "stale embedding model"}

        if not all(
            (
                config.target_vector_backend,
                config.target_vector_store_fingerprint,
                config.target_model_fingerprint,
            )
        ):
            updated_target = await config_service.update_embedding_generation(
                expected_version=config.version,
                expected_rebuild_id=config.rebuild_id,
                expected_statuses={VectorizationStatus.VALIDATING.value},
                target_vector_backend=target_backend,
                target_vector_store_fingerprint=target_store_fingerprint,
                target_model_fingerprint=target_model_fingerprint,
            )
            if updated_target is None:
                return {"success": False, "skipped": "stale config version"}
            config = updated_target
        force_rebuild = force_rebuild or config.target_force_rebuild

        vector_client, vector_error = ensure_vector_client(ctx)

        # Validate provider
        from glean_vector.services import EmbeddingValidationService

        validation_service = EmbeddingValidationService()

        async def set_validation_error(message: str) -> None:
            await config_service.update_embedding_generation(
                expected_version=config.version,
                expected_rebuild_id=config.rebuild_id,
                expected_statuses={VectorizationStatus.VALIDATING.value},
                status=VectorizationStatus.ERROR,
                last_error=message,
                last_error_at=datetime.now(UTC),
                error_count=config.error_count + 1,
                target_vector_backend=None,
                target_vector_store_fingerprint=None,
                target_model_fingerprint=None,
                target_force_rebuild=False,
                rebuild_id=None,
                rebuild_started_at=None,
                rebuild_phase=None,
            )

        # Validate provider
        provider_result = await validation_service.validate_provider(config)
        if not provider_result.success:
            await set_validation_error(f"Provider validation failed: {provider_result.message}")
            return {"success": False, "error": provider_result.message}

        # Validate vector backend
        if vector_client:
            backend_result = await validation_service.validate_vector_backend(
                config.dimension, config.provider, config.model
            )
            if not backend_result.success:
                await set_validation_error(
                    f"Vector backend validation failed: {backend_result.message}"
                )
                return {"success": False, "error": backend_result.message}
        else:
            error = "Vector client not available"
            if vector_error:
                error = f"{error}: {vector_error}"
            await set_validation_error(error)
            return {"success": False, "error": error}

        # Provider validation can be slow. Do not let a result from an obsolete
        # generation change state or enqueue destructive work.
        session.expire_all()
        latest = await config_service.get(EmbeddingConfig)
        if (
            latest.version != config.version
            or latest.rebuild_id != config.rebuild_id
            or latest.status != VectorizationStatus.VALIDATING
            or not latest.enabled
            or latest.target_vector_backend != target_backend
            or latest.target_vector_store_fingerprint != target_store_fingerprint
            or latest.target_model_fingerprint != target_model_fingerprint
        ):
            return {"success": False, "skipped": "stale config version"}
        config = latest

        # Validation passed, check if rebuild is actually needed.
        # Prefer backend validation result (async, backend-aware) when available,
        # then fall back to client-level compatibility checks.
        backend_details = backend_result.details

        details_has_compat = "is_compatible" in backend_details
        details_has_exists = "collections_exist" in backend_details

        if details_has_compat and details_has_exists:
            is_compatible = bool(backend_details.get("is_compatible"))
            collections_exist = bool(backend_details.get("collections_exist"))
            reason = backend_details.get("compatibility_reason")
        else:
            is_compatible, reason = vector_client.check_model_compatibility(
                config.dimension, config.provider, config.model
            )
            collections_exist = vector_client.collections_exist()

        backend_rebuild_required = (
            config.vector_backend is not None and config.vector_backend.lower() != runtime_backend
        )
        backend_rebuild_required = backend_rebuild_required or (
            config.vector_store_fingerprint is not None
            and config.vector_store_fingerprint != runtime_store_fingerprint
        )
        backend_rebuild_required = backend_rebuild_required or (
            config.model_fingerprint is not None
            and config.model_fingerprint != runtime_model_fingerprint
        )
        if config.vector_backend is None and runtime_backend == "pgvector":
            entry_count_result = await session.execute(select(func.count()).select_from(Entry))
            backend_rebuild_required = int(entry_count_result.scalar_one()) > 0

        if backend_rebuild_required:
            reason = (
                f"vector backend changed from {config.vector_backend or 'legacy/unknown'} "
                f"to {runtime_backend}"
            )

        if (
            is_compatible
            and collections_exist
            and not force_rebuild
            and not backend_rebuild_required
        ):
            # Collections exist and are compatible - no rebuild needed
            logger.info(
                "Collections already compatible with config, skipping rebuild. "
                f"model={config.provider}:{config.model}, dimension={config.dimension}"
            )
            updated = await config_service.update_embedding_generation(
                expected_version=config.version,
                expected_rebuild_id=config.rebuild_id,
                expected_statuses={VectorizationStatus.VALIDATING.value},
                status=VectorizationStatus.IDLE,
                vector_backend=runtime_backend,
                vector_store_fingerprint=runtime_store_fingerprint,
                model_fingerprint=runtime_model_fingerprint,
                target_vector_backend=None,
                target_vector_store_fingerprint=None,
                target_model_fingerprint=None,
                target_force_rebuild=False,
                rebuild_id=None,
                rebuild_started_at=None,
                rebuild_phase=None,
            )
            if updated is None:
                return {"success": False, "skipped": "stale config version"}
            return {
                "success": True,
                "message": "Collections already compatible, no rebuild needed",
                "skipped_rebuild": True,
            }

        if force_rebuild and is_compatible and collections_exist:
            logger.info(
                "Force rebuild requested despite compatible collections. "
                f"model={config.provider}:{config.model}, dimension={config.dimension}"
            )

        # Rebuild needed: either collections don't exist or model changed
        logger.info(
            f"Rebuild required: {reason or 'collections do not exist'}. Triggering rebuild..."
        )

        if redis is None:
            await set_validation_error("Redis unavailable; embedding rebuild could not be queued")
            return {"success": False, "error": "Redis unavailable"}

        try:
            await redis.enqueue_job(
                "rebuild_embeddings",
                expected_version=config.version,
                expected_backend=target_backend,
                expected_store_fingerprint=target_store_fingerprint,
                expected_model_fingerprint=target_model_fingerprint,
                _job_id=f"rebuild_{config.version}",
            )
        except Exception as error:
            await set_validation_error(f"Failed to queue embedding rebuild: {error}")
            return {"success": False, "error": str(error)}

        return {"success": True, "message": "Validation passed, rebuild queued"}

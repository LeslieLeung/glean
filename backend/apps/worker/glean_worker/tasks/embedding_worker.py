"""Embedding generation worker tasks."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from glean_core import get_logger
from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus
from glean_core.services import TypedConfigService
from glean_database.session import get_session_context
from glean_vector.clients.embedding_client import EmbeddingClient
from glean_vector.config import EmbeddingConfig as EmbeddingSettings
from glean_vector.services.embedding_service import EmbeddingService

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
    is_enabled = config.enabled and config.status in (
        VectorizationStatus.IDLE,
        VectorizationStatus.REBUILDING,
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


async def _handle_embedding_error(session: AsyncSession, error: Exception) -> None:
    """
    Handle embedding error with circuit breaker logic.

    After CONSECUTIVE_FAILURES_THRESHOLD failures, sets status to ERROR.
    """
    config_service = TypedConfigService(session)
    config = await config_service.get(EmbeddingConfig)

    new_error_count = config.error_count + 1

    if new_error_count >= CONSECUTIVE_FAILURES_THRESHOLD:
        # Circuit breaker: set status to ERROR
        logger.warning(f"Circuit breaker triggered after {new_error_count} consecutive failures")
        await config_service.set_embedding_status(
            VectorizationStatus.ERROR.value,
            error=f"Circuit breaker: {str(error)}",
        )
    else:
        # Just increment error count
        await config_service.update(EmbeddingConfig, error_count=new_error_count)


async def _reset_error_count(session: AsyncSession) -> None:
    """Reset error count on successful operation."""
    config_service = TypedConfigService(session)
    config = await config_service.get(EmbeddingConfig)

    if config.error_count > 0:
        await config_service.update(EmbeddingConfig, error_count=0)


async def _safe_handle_error(session: AsyncSession, error: Exception) -> None:
    """Handle embedding error, recovering from a poisoned session first.

    When a prior DB operation fails, asyncpg puts the connection into a
    failed-transaction state.  This helper rolls back before touching the
    session so the circuit-breaker logic can still read/write config.
    """
    import contextlib

    with contextlib.suppress(Exception):
        await session.rollback()
    try:
        await _handle_embedding_error(session, error)
    except Exception:
        logger.warning("Could not update circuit breaker after error", exc_info=True)


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
        return {"success": False, "entry_id": entry_id, "error": error}

    async with get_session_context() as session:
        # Check if vectorization is enabled
        is_enabled, config = await _check_vectorization_enabled(session)
        if not is_enabled:
            logger.debug(f"Vectorization disabled, skipping embedding for {entry_id}")
            return {"success": False, "entry_id": entry_id, "error": "Vectorization disabled"}

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
            )

            success = await embedding_service.generate_embedding(entry_id)

            if success:
                await _reset_error_count(session)

            return {"success": success, "entry_id": entry_id}

        except Exception as e:
            # Infrastructure error (API / vector backend).  The entry is
            # already marked "failed" by the service layer.  Count toward
            # the circuit breaker but do NOT re-raise — arq retries are
            # wasteful when the backend is down; the entry will be picked
            # up later by retry_failed_embeddings or the next rebuild.
            error_msg = str(e)
            logger.error(
                f"Failed to generate embedding for entry {entry_id}: {error_msg}",
                exc_info=True,
            )
            # Session may be in a failed transaction state; rollback first.
            await _safe_handle_error(session, e)
            return {"success": False, "entry_id": entry_id, "error": error_msg}

        finally:
            await embedding_client.close()


async def batch_generate_embeddings(ctx: dict[str, Any], limit: int = 100) -> dict[str, int | str]:
    """
    Batch generate embeddings for pending entries.

    Args:
        ctx: Worker context
        limit: Maximum number of entries to process

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
            logger.debug("Vectorization disabled, skipping batch generate")
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
            )

            result = await embedding_service.batch_generate(limit=limit)

            processed = result.get("processed", 0)
            failed = result.get("failed", 0)

            if processed > 0:
                await _reset_error_count(session)
            elif failed > 0:
                # Entire batch failed — count toward circuit breaker.
                # Session may be dirty; rollback before using it for config.
                await _safe_handle_error(
                    session,
                    RuntimeError(f"Batch: all {failed} entries failed, 0 succeeded"),
                )

            return result  # type: ignore[return-value]

        except Exception as e:
            logger.error(f"Failed to batch generate embeddings: {e}")
            await _safe_handle_error(session, e)
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
            )

            result = await embedding_service.retry_failed(limit=limit)

            processed = result.get("processed", 0)
            failed = result.get("failed", 0)

            if processed > 0:
                await _reset_error_count(session)
            elif failed > 0:
                await _safe_handle_error(
                    session,
                    RuntimeError(f"Retry batch: all {failed} entries failed, 0 succeeded"),
                )

            return result  # type: ignore[return-value]

        except Exception as e:
            logger.error(f"Failed to retry failed embeddings: {e}")
            await _safe_handle_error(session, e)
            return {"processed": 0, "failed": 0, "error": str(e)}

        finally:
            await embedding_client.close()


async def validate_and_rebuild_embeddings(
    ctx: dict[str, Any], force_rebuild: bool = False
) -> dict[str, Any]:
    """
    Validate embedding config and trigger rebuild if valid.

    This task is triggered when vectorization is enabled or config is changed.
    When force_rebuild is True (explicit user action), the compatibility check
    is skipped and a full rebuild is always triggered.
    """
    vector_client, vector_error = ensure_vector_client(ctx)
    redis = ctx.get("redis")

    async with get_session_context() as session:
        config_service = TypedConfigService(session)
        config = await config_service.get(EmbeddingConfig)

        if not config.enabled:
            return {"success": False, "error": "Vectorization is not enabled"}

        # Validate provider
        from glean_vector.services import EmbeddingValidationService

        validation_service = EmbeddingValidationService()

        # Validate provider
        provider_result = await validation_service.validate_provider(config)
        if not provider_result.success:
            await config_service.set_embedding_status(
                VectorizationStatus.ERROR.value,
                error=f"Provider validation failed: {provider_result.message}",
            )
            return {"success": False, "error": provider_result.message}

        # Validate vector backend
        if vector_client:
            backend_result = await validation_service.validate_vector_backend(
                config.dimension, config.provider, config.model
            )
            if not backend_result.success:
                await config_service.set_embedding_status(
                    VectorizationStatus.ERROR.value,
                    error=f"Vector backend validation failed: {backend_result.message}",
                )
                return {"success": False, "error": backend_result.message}
        else:
            error = "Vector client not available"
            if vector_error:
                error = f"{error}: {vector_error}"
            await config_service.set_embedding_status(
                VectorizationStatus.ERROR.value,
                error=error,
            )
            return {"success": False, "error": error}

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

        if is_compatible and collections_exist and not force_rebuild:
            # Collections exist and are compatible - no rebuild needed
            logger.info(
                "Collections already compatible with config, skipping rebuild. "
                f"model={config.provider}:{config.model}, dimension={config.dimension}"
            )
            await config_service.update(EmbeddingConfig, status=VectorizationStatus.IDLE)
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

        if redis:
            await redis.enqueue_job("rebuild_embeddings")

        return {"success": True, "message": "Validation passed, rebuild queued"}

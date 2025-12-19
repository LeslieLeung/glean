"""Embedding generation worker tasks."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from glean_core import get_logger
from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus
from glean_core.services import TypedConfigService
from glean_database.session import get_session
from glean_vector.clients.embedding_client import EmbeddingClient
from glean_vector.clients.milvus_client import MilvusClient
from glean_vector.config import EmbeddingConfig as EmbeddingSettings
from glean_vector.services.embedding_service import EmbeddingService

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


async def generate_entry_embedding(ctx: dict[str, Any], entry_id: str) -> dict[str, Any]:
    """
    Generate embedding for a single entry.

    Args:
        ctx: Worker context
        entry_id: Entry UUID

    Returns:
        Result dictionary
    """
    milvus_client: MilvusClient | None = ctx.get("milvus_client")
    if not milvus_client:
        return {"success": False, "entry_id": entry_id, "error": "Milvus unavailable"}

    async with get_session() as session:
        # Check if vectorization is enabled
        is_enabled, config = await _check_vectorization_enabled(session)
        if not is_enabled:
            logger.debug(f"Vectorization disabled, skipping embedding for {entry_id}")
            return {"success": False, "entry_id": entry_id, "error": "Vectorization disabled"}

        settings, rate_limit = await _load_embedding_settings(config)
        embedding_client = EmbeddingClient(config=settings, rate_limit=rate_limit)

        try:
            # Ensure Milvus collections exist with correct model
            await milvus_client.ensure_collections(
                settings.dimension, settings.provider, settings.model
            )

            embedding_service = EmbeddingService(
                db_session=session,
                embedding_client=embedding_client,
                milvus_client=milvus_client,
            )

            success = await embedding_service.generate_embedding(entry_id)

            if success:
                # Reset error count on success
                await _reset_error_count(session)

            return {"success": success, "entry_id": entry_id}

        except Exception as e:
            error_msg = str(e)
            logger.error(
                f"Failed to generate embedding for entry {entry_id}: {error_msg}",
                exc_info=True,  # Include full traceback
            )
            await _handle_embedding_error(session, e)
            raise

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
    milvus_client: MilvusClient | None = ctx.get("milvus_client")
    if not milvus_client:
        return {"processed": 0, "failed": 0, "error": "Milvus unavailable"}

    async with get_session() as session:
        # Check if vectorization is enabled
        is_enabled, config = await _check_vectorization_enabled(session)
        if not is_enabled:
            logger.debug("Vectorization disabled, skipping batch generate")
            return {"processed": 0, "failed": 0, "skipped": "Vectorization disabled"}

        settings, rate_limit = await _load_embedding_settings(config)
        embedding_client = EmbeddingClient(config=settings, rate_limit=rate_limit)

        try:
            # Ensure Milvus collections exist with correct model
            await milvus_client.ensure_collections(
                settings.dimension, settings.provider, settings.model
            )

            embedding_service = EmbeddingService(
                db_session=session,
                embedding_client=embedding_client,
                milvus_client=milvus_client,
            )

            result = await embedding_service.batch_generate(limit=limit)

            if result.get("processed", 0) > 0:
                # Reset error count on successful batch
                await _reset_error_count(session)

            return result  # type: ignore[return-value]

        except Exception as e:
            logger.error(f"Failed to batch generate embeddings: {e}")
            await _handle_embedding_error(session, e)
            raise

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
    milvus_client: MilvusClient | None = ctx.get("milvus_client")
    if not milvus_client:
        return {"processed": 0, "failed": 0, "error": "Milvus unavailable"}

    async with get_session() as session:
        # Check if vectorization is enabled
        is_enabled, config = await _check_vectorization_enabled(session)
        if not is_enabled:
            logger.debug("Vectorization disabled, skipping retry")
            return {"processed": 0, "failed": 0, "skipped": "Vectorization disabled"}

        settings, rate_limit = await _load_embedding_settings(config)
        embedding_client = EmbeddingClient(config=settings, rate_limit=rate_limit)

        try:
            # Ensure Milvus collections exist with correct model
            await milvus_client.ensure_collections(
                settings.dimension, settings.provider, settings.model
            )

            embedding_service = EmbeddingService(
                db_session=session,
                embedding_client=embedding_client,
                milvus_client=milvus_client,
            )

            result = await embedding_service.retry_failed(limit=limit)

            if result.get("processed", 0) > 0:
                await _reset_error_count(session)

            return result  # type: ignore[return-value]

        except Exception as e:
            logger.error(f"Failed to retry failed embeddings: {e}")
            await _handle_embedding_error(session, e)
            raise

        finally:
            await embedding_client.close()


async def validate_and_rebuild_embeddings(ctx: dict[str, Any]) -> dict[str, Any]:
    """
    Validate embedding config and trigger rebuild if valid.

    This task is triggered when vectorization is enabled or config is changed.
    """
    milvus_client: MilvusClient | None = ctx.get("milvus_client")
    redis = ctx.get("redis")

    async with get_session() as session:
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

        # Validate Milvus
        if milvus_client:
            milvus_result = await validation_service.validate_milvus(
                config.dimension, config.provider, config.model
            )
            if not milvus_result.success:
                await config_service.set_embedding_status(
                    VectorizationStatus.ERROR.value,
                    error=f"Milvus validation failed: {milvus_result.message}",
                )
                return {"success": False, "error": milvus_result.message}
        else:
            await config_service.set_embedding_status(
                VectorizationStatus.ERROR.value,
                error="Milvus client not available",
            )
            return {"success": False, "error": "Milvus client not available"}

        # Validation passed, trigger rebuild
        logger.info("Validation passed, triggering rebuild")

        if redis:
            await redis.enqueue_job("rebuild_embeddings")

        return {"success": True, "message": "Validation passed, rebuild queued"}

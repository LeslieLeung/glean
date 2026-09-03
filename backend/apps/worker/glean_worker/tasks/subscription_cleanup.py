"""
Subscription cleanup tasks.

This module handles cleanup of orphan data when subscriptions are deleted,
particularly cleaning up vector embeddings for deleted entries.
"""

from typing import Any

from arq import Retry
from sqlalchemy import delete

from glean_core import get_logger
from glean_core.schemas.config import EmbeddingConfig
from glean_core.services import TypedConfigService
from glean_database.models import VectorCleanupPending
from glean_database.session import get_session_context
from glean_vector.config import (
    is_active_embedding_model,
    is_active_vector_backend,
)

from ._vector_client import ensure_vector_client

logger = get_logger(__name__)


async def cleanup_orphan_embeddings(
    ctx: dict[str, Any], feed_id: str, entry_ids: list[str]
) -> dict[str, Any]:
    """
    Clean up vector embeddings for deleted entries.

    This task is called when a feed is deleted (no more subscribers).
    Since the entries are deleted via CASCADE from the database,
    we need to manually clean up their embeddings from vector storage.

    Args:
        ctx: Worker context with vector_client.
        feed_id: The deleted feed ID (for logging).
        entry_ids: List of entry IDs whose embeddings should be deleted.

    Returns:
        Result dict with success status and counts.
    """
    try:
        async with get_session_context() as session:
            config = await TypedConfigService(session).get(EmbeddingConfig)
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
            raise Retry(defer=30)

        vector_client, vector_error = ensure_vector_client(ctx)
        if not vector_client:
            raise Retry(defer=30) from RuntimeError(
                f"Vector backend unavailable: {vector_error or 'unknown error'}"
            )
        await vector_client.ensure_collections(
            config.dimension,
            config.provider,
            config.model,
        )
    except Exception as e:
        logger.warning(
            "Could not initialize vector storage for embedding cleanup",
            extra={"feed_id": feed_id, "error": str(e)},
        )
        if isinstance(e, Retry):
            raise
        raise Retry(defer=30) from e

    deleted_count = 0
    failed_count = 0

    for entry_id in entry_ids:
        try:
            await vector_client.delete_entry_embedding(entry_id)
            deleted_count += 1
        except Exception as e:
            logger.warning(f"Failed to delete embedding for entry {entry_id}: {e}")
            failed_count += 1

    logger.info(
        f"Cleaned up embeddings for feed {feed_id}: deleted={deleted_count}, failed={failed_count}"
    )

    if failed_count:
        raise Retry(defer=30)

    async with get_session_context() as session:
        await session.execute(
            delete(VectorCleanupPending).where(VectorCleanupPending.entry_id.in_(entry_ids))
        )
        await session.commit()

    return {
        "success": failed_count == 0,
        "feed_id": feed_id,
        "deleted": deleted_count,
        "failed": failed_count,
    }

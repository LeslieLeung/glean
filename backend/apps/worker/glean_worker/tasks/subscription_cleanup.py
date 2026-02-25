"""
Subscription cleanup tasks.

This module handles cleanup of orphan data when subscriptions are deleted,
particularly cleaning up vector embeddings for deleted entries.
"""

from typing import Any

from glean_core import get_logger

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
    vector_client, vector_error = ensure_vector_client(ctx)
    if not vector_client:
        if vector_error:
            logger.warning(
                "Vector client not available, skipping embedding cleanup",
                extra={"feed_id": feed_id, "error": vector_error},
            )
            return {
                "success": False,
                "error": f"Vector backend unavailable: {vector_error}",
                "feed_id": feed_id,
            }
        logger.warning("Vector client not available, skipping embedding cleanup")
        return {"success": False, "error": "Vector backend unavailable", "feed_id": feed_id}

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

    return {
        "success": True,
        "feed_id": feed_id,
        "deleted": deleted_count,
        "failed": failed_count,
    }

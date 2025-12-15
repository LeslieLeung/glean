"""
Subscription cleanup tasks.

This module handles cleanup of orphan data when subscriptions are deleted,
particularly cleaning up Milvus embeddings for deleted entries.
"""

from typing import Any

from glean_core import get_logger

logger = get_logger(__name__)


async def cleanup_orphan_embeddings(
    ctx: dict[str, Any], feed_id: str, entry_ids: list[str]
) -> dict[str, Any]:
    """
    Clean up Milvus embeddings for deleted entries.

    This task is called when a feed is deleted (no more subscribers).
    Since the entries are deleted via CASCADE from the database,
    we need to manually clean up their embeddings from Milvus.

    Args:
        ctx: Worker context with milvus_client.
        feed_id: The deleted feed ID (for logging).
        entry_ids: List of entry IDs whose embeddings should be deleted.

    Returns:
        Result dict with success status and counts.
    """
    milvus_client = ctx.get("milvus_client")
    if not milvus_client:
        logger.warning("Milvus client not available, skipping embedding cleanup")
        return {"success": False, "error": "Milvus unavailable", "feed_id": feed_id}

    deleted_count = 0
    failed_count = 0

    for entry_id in entry_ids:
        try:
            await milvus_client.delete_entry_embedding(entry_id)
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

"""
On-demand full-text extraction for feed entries.
"""

from typing import Any

from sqlalchemy import select

from glean_core import get_logger
from glean_database.models import Entry, Subscription
from glean_database.session import get_session_context
from glean_rss import fetch_and_extract_fulltext

logger = get_logger(__name__)


async def extract_entry_fulltext(
    ctx: dict[str, Any], user_id: str, entry_id: str
) -> dict[str, str]:
    """
    Extract full article content for a specific entry and persist it.

    Args:
        ctx: Worker context.
        user_id: Requesting user ID, used for subscription authorization.
        entry_id: Entry ID to extract full text for.

    Returns:
        Operation status payload.
    """
    async with get_session_context() as session:
        stmt = (
            select(Entry)
            .join(Subscription, Subscription.feed_id == Entry.feed_id)
            .where(Entry.id == entry_id, Subscription.user_id == user_id)
        )
        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()

        if not entry:
            logger.warning(
                "Entry not found or inaccessible", extra={"entry_id": entry_id, "user_id": user_id}
            )
            return {"status": "not_found"}

        if not entry.url:
            logger.warning("Entry has no URL for extraction", extra={"entry_id": entry_id})
            return {"status": "no_url"}

        logger.info(
            "Starting on-demand full-text extraction",
            extra={"entry_id": entry_id, "url": entry.url},
        )
        extracted_content = await fetch_and_extract_fulltext(entry.url)
        if not extracted_content:
            logger.warning(
                "Full-text extraction returned empty content", extra={"entry_id": entry_id}
            )
            return {"status": "empty"}

        entry.readability_content = extracted_content
        # Regenerate embedding from refreshed content when vectorization is enabled.
        entry.embedding_status = "pending"

        redis = ctx.get("redis")
        if redis:
            await redis.enqueue_job("generate_entry_embedding", entry.id)

        logger.info(
            "On-demand full-text extraction completed",
            extra={"entry_id": entry_id, "content_length": len(extracted_content)},
        )
        return {"status": "updated"}

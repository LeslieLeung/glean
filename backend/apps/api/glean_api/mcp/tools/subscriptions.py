"""
MCP tools for subscription operations.

Provides listing functionality for RSS feed subscriptions.
"""

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from glean_core import get_logger
from glean_database.models import Entry, Subscription, UserEntry
from glean_database.session import get_session_context

from ..auth import extract_user_id_from_scopes
from ..server import MCPContext

logger = get_logger(__name__)


async def list_subscriptions(
    ctx: Context[ServerSession, MCPContext],
    folder_id: str | None = None,
) -> list[dict[str, str | int | None]]:
    """
    List all RSS feed subscriptions.

    Args:
        ctx: MCP context.
        folder_id: Optional folder ID to filter subscriptions.
                   Pass empty string to get ungrouped subscriptions only.

    Returns:
        List of subscriptions with id, feed_id, feed_title, feed_url, unread_count.
    """
    # Extract user_id from authentication context
    access_token = get_access_token()
    if not access_token:
        return [{"error": "Authentication required"}]

    user_id = extract_user_id_from_scopes(access_token.scopes)
    if not user_id:
        return [{"error": "Invalid authentication token"}]

    async with get_session_context() as session:
        # Build query
        stmt = (
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .options(selectinload(Subscription.feed))
            .order_by(Subscription.created_at.desc())
        )

        # Apply folder filter if provided
        if folder_id == "":
            # Empty string means get ungrouped subscriptions
            stmt = stmt.where(Subscription.folder_id.is_(None))
        elif folder_id is not None:
            stmt = stmt.where(Subscription.folder_id == folder_id)

        result = await session.execute(stmt)
        subscriptions = result.scalars().all()

        # Get unread counts for all feeds in a single query
        feed_ids = [sub.feed_id for sub in subscriptions]
        unread_counts_stmt = (
            select(
                Entry.feed_id,
                func.count(Entry.id).label("unread_count"),
            )
            .where(Entry.feed_id.in_(feed_ids))
            .outerjoin(
                UserEntry,
                (UserEntry.entry_id == Entry.id) & (UserEntry.user_id == user_id),
            )
            .where((UserEntry.is_read.is_(False)) | (UserEntry.is_read.is_(None)))
            .group_by(Entry.feed_id)
        )
        unread_result = await session.execute(unread_counts_stmt)
        unread_counts_by_feed = {row[0]: row[1] for row in unread_result.all()}

        # Build response with unread counts
        responses: list[dict[str, str | int | None]] = []
        for sub in subscriptions:
            unread_count = unread_counts_by_feed.get(sub.feed_id, 0)

            responses.append(
                {
                    "id": str(sub.id),
                    "feed_id": str(sub.feed_id),
                    "feed_title": sub.custom_title or sub.feed.title if sub.feed else None,
                    "feed_url": sub.feed.url if sub.feed else None,
                    "unread_count": unread_count,
                    "folder_id": str(sub.folder_id) if sub.folder_id else None,
                }
            )

        logger.info(
            "MCP list_subscriptions completed",
            extra={
                "user_id": user_id,
                "subscription_count": len(responses),
            },
        )

        return responses

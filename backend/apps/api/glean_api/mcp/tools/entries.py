"""
MCP tools for entry operations.

Provides search, get, and list functionality for RSS feed entries.
"""

from datetime import datetime

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from sqlalchemy import desc, func, select

from glean_core import get_logger
from glean_database.models import Entry, Feed, Subscription, UserEntry
from glean_database.session import get_session_context

from ..auth import extract_user_id_from_scopes
from ..server import MCPContext

logger = get_logger(__name__)


def escape_like_pattern(pattern: str) -> str:
    """
    Escape special LIKE wildcards in a search pattern.

    Args:
        pattern: The search pattern to escape.

    Returns:
        Escaped pattern safe for use in LIKE queries.
    """
    # Escape % and _ characters to prevent LIKE injection
    return pattern.replace("%", r"\%").replace("_", r"\_")


async def search_entries(
    ctx: Context[ServerSession, MCPContext],
    query: str,
    feed_id: str | None = None,
    limit: int = 20,
) -> list[dict[str, str | bool | None]]:
    """
    Search articles by keyword in title or content.

    Args:
        ctx: MCP context.
        query: Search query string to match against article titles and content.
        feed_id: Optional feed ID to filter results to a specific feed.
        limit: Maximum number of results to return (default: 20, max: 100).

    Returns:
        List of matching articles with id, title, url, summary, published_at, feed_title, is_read.
    """
    # Extract user_id from authentication context
    access_token = get_access_token()
    if not access_token:
        return [{"error": "Authentication required"}]

    user_id = extract_user_id_from_scopes(access_token.scopes)
    if not user_id:
        return [{"error": "Invalid authentication token"}]

    # Validate search query
    if not query or len(query) < 2:
        return [{"error": "Search query must be at least 2 characters"}]
    if len(query) > 200:
        return [{"error": "Search query must be at most 200 characters"}]

    # Clamp limit
    limit = max(1, min(limit, 100))

    async with get_session_context() as session:
        # Get user's subscribed feed IDs
        sub_stmt = select(Subscription.feed_id).where(Subscription.user_id == user_id)
        result = await session.execute(sub_stmt)
        feed_ids = [row[0] for row in result.all()]

        if not feed_ids:
            return []

        # Build search query with escaped wildcards
        escaped_query = escape_like_pattern(query.lower())
        search_term = f"%{escaped_query}%"
        stmt = (
            select(Entry, UserEntry, Feed.title.label("feed_title"))
            .join(Feed, Entry.feed_id == Feed.id)
            .outerjoin(
                UserEntry,
                (Entry.id == UserEntry.entry_id) & (UserEntry.user_id == user_id),
            )
            .where(Entry.feed_id.in_(feed_ids))
            .where(
                (func.lower(Entry.title).like(search_term))
                | (func.lower(Entry.content).like(search_term))
                | (func.lower(Entry.summary).like(search_term))
            )
        )

        # Filter by feed_id if provided
        if feed_id:
            stmt = stmt.where(Entry.feed_id == feed_id)

        # Order and limit
        stmt = stmt.order_by(desc(Entry.published_at)).limit(limit)

        result = await session.execute(stmt)
        rows = result.all()

        entries: list[dict[str, str | bool | None]] = []
        for entry, user_entry, feed_title in rows:
            entries.append(
                {
                    "id": str(entry.id),
                    "title": str(entry.title),
                    "url": str(entry.url),
                    "summary": entry.summary[:500] if entry.summary else None,
                    "published_at": entry.published_at.isoformat() if entry.published_at else None,
                    "feed_title": feed_title,
                    "is_read": bool(user_entry.is_read) if user_entry else False,
                }
            )

        logger.info(
            "MCP search_entries completed",
            extra={
                "user_id": user_id,
                "query": query,
                "result_count": len(entries),
            },
        )

        return entries


async def get_entry(
    ctx: Context[ServerSession, MCPContext],
    entry_id: str,
) -> dict[str, str | bool | None]:
    """
    Get full details of a specific article.

    Args:
        ctx: MCP context.
        entry_id: The unique identifier of the article to retrieve.

    Returns:
        Article details including id, title, url, content, summary, author,
        published_at, feed_title, and is_read status.
    """
    # Extract user_id from authentication context
    access_token = get_access_token()
    if not access_token:
        return {"error": "Authentication required"}

    user_id = extract_user_id_from_scopes(access_token.scopes)
    if not user_id:
        return {"error": "Invalid authentication token"}

    async with get_session_context() as session:
        # Get entry with feed info
        stmt = (
            select(Entry, UserEntry, Feed.title.label("feed_title"))
            .join(Feed, Entry.feed_id == Feed.id)
            .outerjoin(
                UserEntry,
                (Entry.id == UserEntry.entry_id) & (UserEntry.user_id == user_id),
            )
            .where(Entry.id == entry_id)
        )

        result = await session.execute(stmt)
        row = result.one_or_none()

        if not row:
            return {"error": "Entry not found"}

        entry, user_entry, feed_title = row

        # Verify user is subscribed to this feed
        sub_stmt = select(Subscription).where(
            Subscription.user_id == user_id, Subscription.feed_id == entry.feed_id
        )
        sub_result = await session.execute(sub_stmt)
        if not sub_result.scalar_one_or_none():
            return {"error": "Not subscribed to this feed"}

        logger.info(
            "MCP get_entry completed",
            extra={"user_id": user_id, "entry_id": entry_id},
        )

        return {
            "id": str(entry.id),
            "title": str(entry.title),
            "url": str(entry.url),
            "content": entry.content,
            "summary": entry.summary,
            "author": entry.author,
            "published_at": entry.published_at.isoformat() if entry.published_at else None,
            "feed_title": feed_title,
            "is_read": bool(user_entry.is_read) if user_entry else False,
        }


async def list_entries_by_date(
    ctx: Context[ServerSession, MCPContext],
    start_date: str,
    end_date: str,
    feed_id: str | None = None,
    is_read: bool | None = None,
    limit: int = 50,
) -> list[dict[str, str | bool | None]]:
    """
    List articles within a date range.

    Args:
        ctx: MCP context.
        start_date: Start date in ISO format (YYYY-MM-DD).
        end_date: End date in ISO format (YYYY-MM-DD).
        feed_id: Optional feed ID to filter results.
        is_read: Optional filter for read status (True=read only, False=unread only, None=all).
        limit: Maximum number of results (default: 50, max: 200).

    Returns:
        List of articles matching the criteria.
    """
    # Extract user_id from authentication context
    access_token = get_access_token()
    if not access_token:
        return [{"error": "Authentication required"}]

    user_id = extract_user_id_from_scopes(access_token.scopes)
    if not user_id:
        return [{"error": "Invalid authentication token"}]

    # Parse dates
    try:
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)
        # Set end_date to end of day
        end_dt = end_dt.replace(hour=23, minute=59, second=59)
    except ValueError:
        return [{"error": "Invalid date format. Use YYYY-MM-DD."}]

    # Validate date range
    if start_dt > end_dt:
        return [{"error": "Start date must be before or equal to end date."}]

    # Limit date range to 1 year to prevent excessive queries
    date_range_days = (end_dt - start_dt).days
    if date_range_days > 365:
        return [{"error": "Date range cannot exceed 365 days."}]

    # Clamp limit
    limit = max(1, min(limit, 200))

    async with get_session_context() as session:
        # Get user's subscribed feed IDs
        sub_stmt = select(Subscription.feed_id).where(Subscription.user_id == user_id)
        result = await session.execute(sub_stmt)
        feed_ids = [row[0] for row in result.all()]

        if not feed_ids:
            return []

        # Build query
        stmt = (
            select(Entry, UserEntry, Feed.title.label("feed_title"))
            .join(Feed, Entry.feed_id == Feed.id)
            .outerjoin(
                UserEntry,
                (Entry.id == UserEntry.entry_id) & (UserEntry.user_id == user_id),
            )
            .where(Entry.feed_id.in_(feed_ids))
            .where(Entry.published_at >= start_dt)
            .where(Entry.published_at <= end_dt)
        )

        # Filter by feed_id if provided
        if feed_id:
            stmt = stmt.where(Entry.feed_id == feed_id)

        # Filter by read status if provided
        if is_read is not None:
            if is_read:
                stmt = stmt.where(UserEntry.is_read.is_(True))
            else:
                stmt = stmt.where((UserEntry.is_read.is_(False)) | (UserEntry.is_read.is_(None)))

        # Order and limit
        stmt = stmt.order_by(desc(Entry.published_at)).limit(limit)

        result = await session.execute(stmt)
        rows = result.all()

        entries: list[dict[str, str | bool | None]] = []
        for entry, user_entry, feed_title in rows:
            entries.append(
                {
                    "id": str(entry.id),
                    "title": str(entry.title),
                    "url": str(entry.url),
                    "summary": entry.summary[:500] if entry.summary else None,
                    "published_at": entry.published_at.isoformat() if entry.published_at else None,
                    "feed_title": feed_title,
                    "is_read": bool(user_entry.is_read) if user_entry else False,
                }
            )

        logger.info(
            "MCP list_entries_by_date completed",
            extra={
                "user_id": user_id,
                "start_date": start_date,
                "end_date": end_date,
                "result_count": len(entries),
            },
        )

        return entries

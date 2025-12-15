"""
Feed fetcher tasks.

Background tasks for fetching and parsing RSS feeds.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from arq import Retry
from sqlalchemy import select

from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus
from glean_core.services import TypedConfigService
from glean_database.models import Entry, Feed, FeedStatus
from glean_database.session import get_session
from glean_rss import fetch_feed, parse_feed


async def _is_vectorization_enabled(session) -> bool:
    """Check if vectorization is enabled and healthy."""
    config_service = TypedConfigService(session)
    config = await config_service.get(EmbeddingConfig)
    return config.enabled and config.status in (
        VectorizationStatus.IDLE,
        VectorizationStatus.REBUILDING,
    )


async def fetch_feed_task(ctx: dict[str, Any], feed_id: str) -> dict[str, str | int]:
    """
    Fetch and parse a single RSS feed.

    Args:
        ctx: Worker context.
        feed_id: Feed identifier to fetch.

    Returns:
        Dictionary with fetch results.
    """
    print(f"[fetch_feed_task] Starting fetch for feed_id: {feed_id}")
    async for session in get_session():
        try:
            # Get feed from database
            stmt = select(Feed).where(Feed.id == feed_id)
            result = await session.execute(stmt)
            feed = result.scalar_one_or_none()

            if not feed:
                print(f"[fetch_feed_task] ERROR: Feed not found: {feed_id}")
                return {"status": "error", "message": "Feed not found"}

            print(f"[fetch_feed_task] Fetching feed: {feed.url}")

            # Fetch feed content
            print(f"[fetch_feed_task] Requesting feed: {feed.url}")
            fetch_result = await fetch_feed(feed.url, feed.etag, feed.last_modified)

            if fetch_result is None:
                # Not modified (304)
                print(f"[fetch_feed_task] Feed not modified (304): {feed.url}")
                feed.last_fetched_at = datetime.now(UTC)
                await session.commit()
                return {"status": "not_modified", "new_entries": 0}

            print("[fetch_feed_task] Feed content received, parsing...")

            content, cache_headers = fetch_result

            # Parse feed
            print("[fetch_feed_task] Parsing feed content...")
            parsed_feed = await parse_feed(content, feed.url)
            print(
                f"[fetch_feed_task] Parsed feed: {parsed_feed.title}, {len(parsed_feed.entries)} entries"
            )

            # Update feed metadata
            print(f"[fetch_feed_task] DEBUG: parsed_feed.icon_url = {parsed_feed.icon_url!r}")
            print(f"[fetch_feed_task] DEBUG: feed.icon_url (before) = {feed.icon_url!r}")
            feed.title = parsed_feed.title or feed.title
            feed.description = parsed_feed.description or feed.description
            feed.site_url = parsed_feed.site_url or feed.site_url
            feed.language = parsed_feed.language or feed.language
            feed.icon_url = parsed_feed.icon_url or feed.icon_url
            print(f"[fetch_feed_task] DEBUG: feed.icon_url (after) = {feed.icon_url!r}")
            feed.status = FeedStatus.ACTIVE
            feed.error_count = 0
            feed.fetch_error_message = None
            feed.last_fetched_at = datetime.now(UTC)

            # Update cache headers
            if cache_headers and "etag" in cache_headers:
                feed.etag = cache_headers["etag"]
            if cache_headers and "last-modified" in cache_headers:
                feed.last_modified = cache_headers["last-modified"]

            # Process entries
            new_entries = 0
            latest_entry_time = feed.last_entry_at

            for parsed_entry in parsed_feed.entries:
                # Check if entry already exists
                stmt = select(Entry).where(
                    Entry.feed_id == feed.id, Entry.guid == parsed_entry.guid
                )
                result = await session.execute(stmt)
                existing_entry = result.scalar_one_or_none()

                if existing_entry:
                    continue

                # Create new entry
                entry = Entry(
                    feed_id=feed.id,
                    guid=parsed_entry.guid,
                    url=parsed_entry.url,
                    title=parsed_entry.title,
                    author=parsed_entry.author,
                    content=parsed_entry.content,
                    summary=parsed_entry.summary,
                    published_at=parsed_entry.published_at,
                )
                session.add(entry)
                await session.flush()  # Get entry ID
                new_entries += 1

                # M3: Queue embedding task for new entry (only if vectorization enabled)
                if ctx.get("milvus_client") and await _is_vectorization_enabled(session):
                    await ctx["redis"].enqueue_job("generate_entry_embedding", entry.id)
                    print(f"[fetch_feed_task] Queued embedding task for entry: {entry.id}")

                # Track latest entry time
                if parsed_entry.published_at and (
                    latest_entry_time is None or parsed_entry.published_at > latest_entry_time
                ):
                    latest_entry_time = parsed_entry.published_at

            # Update last_entry_at and schedule next fetch
            if latest_entry_time:
                feed.last_entry_at = latest_entry_time

            # Schedule next fetch (15 minutes from now)
            feed.next_fetch_at = datetime.now(UTC) + timedelta(minutes=15)

            await session.commit()

            print(
                f"[fetch_feed_task] SUCCESS: Feed {feed.url} - {new_entries} new entries out of {len(parsed_feed.entries)} total"
            )
            return {
                "status": "success",
                "feed_id": feed_id,
                "new_entries": new_entries,
                "total_entries": len(parsed_feed.entries),
            }

        except Exception as e:
            print(
                f"[fetch_feed_task] ERROR: Failed to fetch feed {feed_id}: {type(e).__name__}: {str(e)}"
            )
            # Update feed error status
            stmt = select(Feed).where(Feed.id == feed_id)
            result = await session.execute(stmt)
            feed = result.scalar_one_or_none()

            if feed:
                feed.error_count += 1
                feed.fetch_error_message = str(e)
                feed.last_fetched_at = datetime.now(UTC)

                # Disable feed after 10 consecutive errors
                if feed.error_count >= 10:
                    print(f"[fetch_feed_task] DISABLED: Feed {feed.url} disabled after 10 errors")
                    feed.status = FeedStatus.ERROR

                # Schedule retry with exponential backoff
                retry_minutes = min(60, 15 * (2 ** min(feed.error_count - 1, 5)))
                feed.next_fetch_at = datetime.now(UTC) + timedelta(minutes=retry_minutes)

                print(
                    f"[fetch_feed_task] Scheduling retry in {retry_minutes} minutes (error count: {feed.error_count})"
                )
                await session.commit()

            # Retry the task
            print("[fetch_feed_task] Retrying task in 5 minutes...")
            raise Retry(defer=timedelta(minutes=5)) from None

    # This should never be reached since get_session() always yields
    return {"status": "error", "message": "No database session"}


async def fetch_all_feeds(ctx: dict[str, Any]) -> dict[str, int]:
    """
    Fetch all active feeds.

    Args:
        ctx: Worker context.

    Returns:
        Dictionary with fetch statistics.
    """
    print("[fetch_all_feeds] Starting to fetch all active feeds")
    async for session in get_session():
        # Get all active feeds that are due for fetching
        now = datetime.now(UTC)
        stmt = select(Feed).where(
            Feed.status == FeedStatus.ACTIVE,
            (Feed.next_fetch_at.is_(None)) | (Feed.next_fetch_at <= now),
        )
        result = await session.execute(stmt)
        feeds = result.scalars().all()

        print(f"[fetch_all_feeds] Found {len(feeds)} feeds to fetch")

        # Queue fetch tasks for each feed
        for feed in feeds:
            print(f"[fetch_all_feeds] Queueing feed: {feed.url} (ID: {feed.id})")
            await ctx["redis"].enqueue_job("fetch_feed_task", feed.id)

        print(f"[fetch_all_feeds] Queued {len(feeds)} feeds for fetching")
        return {"feeds_queued": len(feeds)}

    # This should never be reached since get_session() always yields
    return {"feeds_queued": 0}


async def scheduled_fetch(ctx: dict[str, Any]) -> dict[str, int]:
    """
    Scheduled task to fetch all feeds (runs every 15 minutes).

    Args:
        ctx: Worker context.

    Returns:
        Dictionary with fetch statistics.
    """
    print("[scheduled_fetch] Running scheduled feed fetch (every 15 minutes)")
    return await fetch_all_feeds(ctx)


# Export task functions (arq uses the exported name)
fetch_feed_task_exported = fetch_feed_task

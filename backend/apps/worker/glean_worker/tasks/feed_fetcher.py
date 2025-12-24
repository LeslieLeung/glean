"""
Feed fetcher tasks.

Background tasks for fetching and parsing RSS feeds.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from arq import Retry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core import get_logger
from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus
from glean_core.services import TypedConfigService
from glean_database.models import Entry, Feed, FeedStatus
from glean_database.session import get_session_context
from glean_rss import fetch_and_extract_fulltext, fetch_feed, parse_feed, postprocess_html

logger = get_logger(__name__)


async def _is_vectorization_enabled(session: AsyncSession) -> bool:
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
    logger.info("Starting feed fetch", extra={"feed_id": feed_id})
    async with get_session_context() as session:
        try:
            # Get feed from database
            stmt = select(Feed).where(Feed.id == feed_id)
            result = await session.execute(stmt)
            feed = result.scalar_one_or_none()

            if not feed:
                logger.error("Feed not found", extra={"feed_id": feed_id})
                return {"status": "error", "message": "Feed not found"}

            logger.info("Fetching feed", extra={"feed_id": feed_id, "url": feed.url})

            # Fetch feed content
            logger.debug("Requesting feed", extra={"url": feed.url})
            fetch_result = await fetch_feed(feed.url, feed.etag, feed.last_modified)

            if fetch_result is None:
                # Not modified (304)
                logger.info("Feed not modified (304)", extra={"feed_id": feed_id, "url": feed.url})
                feed.last_fetched_at = datetime.now(UTC)
                return {"status": "not_modified", "new_entries": 0}

            logger.debug("Feed content received, parsing...", extra={"feed_id": feed_id})

            content, cache_headers = fetch_result

            # Parse feed
            logger.debug("Parsing feed content...", extra={"feed_id": feed_id})
            parsed_feed = await parse_feed(content, feed.url)
            logger.info(
                "Parsed feed",
                extra={
                    "feed_id": feed_id,
                    "title": parsed_feed.title,
                    "entries_count": len(parsed_feed.entries),
                },
            )

            # Update feed metadata
            logger.debug(
                "Feed metadata",
                extra={
                    "feed_id": feed_id,
                    "parsed_icon_url": parsed_feed.icon_url,
                    "current_icon_url": feed.icon_url,
                },
            )
            feed.title = parsed_feed.title or feed.title
            feed.description = parsed_feed.description or feed.description
            feed.site_url = parsed_feed.site_url or feed.site_url
            feed.language = parsed_feed.language or feed.language
            feed.icon_url = parsed_feed.icon_url or feed.icon_url
            logger.debug(
                "Updated feed metadata", extra={"feed_id": feed_id, "icon_url": feed.icon_url}
            )
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

                # Determine content: fetch full text if feed only provides summary
                entry_content = parsed_entry.content
                if not parsed_entry.has_full_content and parsed_entry.url:
                    logger.info(
                        "Entry has no full content, fetching from URL",
                        extra={"feed_id": feed_id, "url": parsed_entry.url},
                    )
                    try:
                        extracted_content = await fetch_and_extract_fulltext(parsed_entry.url)
                        if extracted_content:
                            entry_content = extracted_content
                            logger.info(
                                "Successfully extracted full text",
                                extra={
                                    "feed_id": feed_id,
                                    "content_length": len(extracted_content),
                                },
                            )
                        else:
                            logger.warning(
                                "Full text extraction returned empty, using summary",
                                extra={"feed_id": feed_id},
                            )
                    except Exception as extract_err:
                        logger.warning(
                            "Full text extraction failed, using summary",
                            extra={"feed_id": feed_id, "error": str(extract_err)},
                        )
                else:
                    # Process content from feed to fix backtick formatting etc.
                    if entry_content:
                        entry_content = await postprocess_html(
                            entry_content, base_url=parsed_entry.url
                        )

                # Create new entry
                entry = Entry(
                    feed_id=feed.id,
                    guid=parsed_entry.guid,
                    url=parsed_entry.url,
                    title=parsed_entry.title,
                    author=parsed_entry.author,
                    content=entry_content,
                    summary=parsed_entry.summary,
                    published_at=parsed_entry.published_at,
                )
                session.add(entry)
                await session.flush()  # Get entry ID
                new_entries += 1

                # M3: Queue embedding task for new entry (only if vectorization enabled)
                if ctx.get("milvus_client") and await _is_vectorization_enabled(session):
                    await ctx["redis"].enqueue_job("generate_entry_embedding", entry.id)
                    logger.debug(
                        "Queued embedding task for entry",
                        extra={"feed_id": feed_id, "entry_id": entry.id},
                    )

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

            logger.info(
                "Successfully fetched feed",
                extra={
                    "feed_id": feed_id,
                    "url": feed.url,
                    "new_entries": new_entries,
                    "total_entries": len(parsed_feed.entries),
                },
            )
            return {
                "status": "success",
                "feed_id": feed_id,
                "new_entries": new_entries,
                "total_entries": len(parsed_feed.entries),
            }

        except Exception as e:
            logger.exception(
                "Failed to fetch feed",
                extra={"feed_id": feed_id},
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
                    logger.warning(
                        "Feed disabled after 10 consecutive errors",
                        extra={"feed_id": feed_id, "url": feed.url},
                    )
                    feed.status = FeedStatus.ERROR

                # Schedule retry with exponential backoff
                retry_minutes = min(60, 15 * (2 ** min(feed.error_count - 1, 5)))
                feed.next_fetch_at = datetime.now(UTC) + timedelta(minutes=retry_minutes)

                logger.info(
                    "Scheduling retry with exponential backoff",
                    extra={
                        "feed_id": feed_id,
                        "retry_minutes": retry_minutes,
                        "error_count": feed.error_count,
                    },
                )

            # Retry the task
            logger.info("Retrying task in 5 minutes", extra={"feed_id": feed_id})
            raise Retry(defer=timedelta(minutes=5)) from None


async def fetch_all_feeds(ctx: dict[str, Any]) -> dict[str, int]:
    """
    Fetch all active feeds.

    Args:
        ctx: Worker context.

    Returns:
        Dictionary with fetch statistics.
    """
    logger.info("Starting to fetch all active feeds")
    async with get_session_context() as session:
        # Get all active feeds that are due for fetching
        now = datetime.now(UTC)
        stmt = select(Feed).where(
            Feed.status == FeedStatus.ACTIVE,
            (Feed.next_fetch_at.is_(None)) | (Feed.next_fetch_at <= now),
        )
        result = await session.execute(stmt)
        feeds = result.scalars().all()

        logger.info("Found feeds to fetch", extra={"count": len(feeds)})

        # Queue fetch tasks for each feed
        for feed in feeds:
            logger.debug("Queueing feed", extra={"feed_id": feed.id, "url": feed.url})
            await ctx["redis"].enqueue_job("fetch_feed_task", feed.id)

        logger.info("Queued feeds for fetching", extra={"count": len(feeds)})
        return {"feeds_queued": len(feeds)}


async def scheduled_fetch(ctx: dict[str, Any]) -> dict[str, int]:
    """
    Scheduled task to fetch all feeds (runs every 15 minutes).

    Args:
        ctx: Worker context.

    Returns:
        Dictionary with fetch statistics.
    """
    logger.info("Running scheduled feed fetch (every 15 minutes)")
    return await fetch_all_feeds(ctx)


# Export task functions (arq uses the exported name)
fetch_feed_task_exported = fetch_feed_task

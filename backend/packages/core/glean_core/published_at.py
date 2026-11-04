"""Publication time used for ordering and display.

A feed date is kept when it is present and not meaningfully in the future.
A missing date, or one further ahead than ``FUTURE_PUBLISHED_AT_TOLERANCE``,
is replaced with the time the article was fetched. That stops undated items
and far-future timestamps from sorting above every real article.
"""

from datetime import UTC, datetime, timedelta

# Clock skew of a few minutes should not rewrite a genuine timestamp.
# Anything further ahead is treated as an abnormal feed date.
FUTURE_PUBLISHED_AT_TOLERANCE = timedelta(minutes=15)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def effective_published_at(
    published_at: datetime | None,
    fetched_at: datetime,
    *,
    now: datetime | None = None,
) -> datetime:
    """Return the feed date, or ``fetched_at`` when that date is unusable.

    Args:
        published_at: Timestamp from the feed. ``None`` when the feed omitted it.
        fetched_at: When this article was pulled. For a stored row this is ``created_at``.
        now: Clock used to decide whether a date is still in the future.

    Returns:
        The timestamp callers should store, sort by, and display.
    """
    current = _as_utc(now or datetime.now(UTC))
    fetched = _as_utc(fetched_at)
    if published_at is None:
        return fetched
    published = _as_utc(published_at)
    if published > current + FUTURE_PUBLISHED_AT_TOLERANCE:
        return fetched
    return published


def publication_time_was_replaced(published_at: datetime | None, resolved: datetime) -> bool:
    """Whether ``resolved`` is the fetch time standing in for an abnormal feed date."""
    if published_at is None:
        return True
    return _as_utc(published_at) != resolved

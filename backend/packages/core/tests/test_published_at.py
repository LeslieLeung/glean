"""Tests for abnormal feed publication times."""

from datetime import UTC, datetime, timedelta

from glean_core.published_at import (
    FUTURE_PUBLISHED_AT_TOLERANCE,
    effective_published_at,
    publication_time_was_replaced,
)


def test_missing_feed_date_uses_fetch_time() -> None:
    fetched_at = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)

    resolved = effective_published_at(None, fetched_at, now=fetched_at)

    assert resolved == fetched_at
    assert publication_time_was_replaced(None, resolved)


def test_past_feed_date_is_kept() -> None:
    fetched_at = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    published_at = datetime(2026, 2, 1, 8, 0, tzinfo=UTC)

    resolved = effective_published_at(published_at, fetched_at, now=fetched_at)

    assert resolved == published_at
    assert not publication_time_was_replaced(published_at, resolved)


def test_small_future_skew_is_kept() -> None:
    now = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    published_at = now + FUTURE_PUBLISHED_AT_TOLERANCE

    resolved = effective_published_at(published_at, now - timedelta(hours=1), now=now)

    assert resolved == published_at


def test_far_future_feed_date_uses_original_fetch_time() -> None:
    fetched_at = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    now = fetched_at + timedelta(days=2)
    published_at = now + timedelta(days=30)

    resolved = effective_published_at(published_at, fetched_at, now=now)

    assert resolved == fetched_at
    assert publication_time_was_replaced(published_at, resolved)


def test_future_date_that_has_since_arrived_is_kept() -> None:
    fetched_at = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    published_at = fetched_at + timedelta(days=1)
    now = published_at + timedelta(hours=1)

    resolved = effective_published_at(published_at, fetched_at, now=now)

    assert resolved == published_at


def test_naive_datetimes_are_treated_as_utc() -> None:
    fetched_at = datetime(2026, 3, 1, 12, 0)
    published_at = datetime(2026, 3, 2, 12, 0)
    now = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)

    resolved = effective_published_at(published_at, fetched_at, now=now)

    assert resolved == datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def test_stored_future_timestamp_is_replaced_on_a_later_refresh() -> None:
    stored = datetime(2027, 1, 1, tzinfo=UTC)
    refresh = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)

    resolved = effective_published_at(stored, refresh, now=refresh)

    assert resolved == refresh
    assert publication_time_was_replaced(stored, resolved)


def test_genuine_past_timestamp_survives_a_later_refresh() -> None:
    stored = datetime(2026, 2, 1, 8, 0, tzinfo=UTC)
    refresh = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)

    resolved = effective_published_at(stored, refresh, now=refresh)

    assert resolved == stored
    assert not publication_time_was_replaced(stored, resolved)


def test_sort_order_places_abnormal_dates_at_fetch_time() -> None:
    now = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
    undated = ("undated", None, now - timedelta(hours=1))
    future = ("future", now + timedelta(days=365), now - timedelta(days=3))
    recent = ("recent", now - timedelta(hours=2), now - timedelta(hours=2))
    older = ("older", now - timedelta(days=10), now - timedelta(days=9))

    ordered = sorted(
        (undated, future, recent, older),
        key=lambda item: effective_published_at(item[1], item[2], now=now),
        reverse=True,
    )

    assert [item[0] for item in ordered] == ["undated", "recent", "future", "older"]

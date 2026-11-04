"""Abnormal feed dates are stored as the fetch time and displayed that way."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from glean_database.models.entry import Entry
from glean_database.models.feed import Feed
from glean_rss.parser import ParsedFeed
from glean_worker.tasks.feed_fetcher import fetch_feed_task


def _parsed_feed() -> ParsedFeed:
    past = datetime(2026, 2, 1, 8, 0, tzinfo=UTC)
    future = datetime(2030, 6, 1, 0, 0, tzinfo=UTC)
    return ParsedFeed(
        {
            "feed": {
                "title": "Abnormal dates",
                "description": "",
                "link": "https://example.com/abnormal",
            },
            "entries": [
                {
                    "id": "kept-past",
                    "link": "https://example.com/abnormal/past",
                    "title": "Real date",
                    "summary": "past",
                    "content": [{"value": "<p>past</p>"}],
                    "published_parsed": past.timetuple(),
                },
                {
                    "id": "replaced-future",
                    "link": "https://example.com/abnormal/future",
                    "title": "Future date",
                    "summary": "future",
                    "content": [{"value": "<p>future</p>"}],
                    "published_parsed": future.timetuple(),
                },
                {
                    "id": "replaced-missing",
                    "link": "https://example.com/abnormal/missing",
                    "title": "Missing date",
                    "summary": "missing",
                    "content": [{"value": "<p>missing</p>"}],
                },
                {
                    "id": "already-stored",
                    "link": "https://example.com/abnormal/stored",
                    "title": "Already stored",
                    "summary": "stored",
                    "content": [{"value": "<p>stored</p>"}],
                    "published_parsed": future.timetuple(),
                },
            ],
        }
    )


@pytest.mark.asyncio
async def test_fetch_replaces_abnormal_dates_and_keeps_original_fetch_time(
    mcp_db_session: AsyncSession,
) -> None:
    """A refresh must not pin an old undated article to the top."""
    original_fetch = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    feed = Feed(
        url="https://example.com/abnormal-dates.xml",
        title="Abnormal dates",
        status="active",
        last_entry_at=datetime(2035, 1, 1, tzinfo=UTC),
    )
    mcp_db_session.add(feed)
    await mcp_db_session.flush()
    stored = Entry(
        feed_id=feed.id,
        guid="already-stored",
        url="https://example.com/abnormal/stored",
        title="Already stored",
        content="<p>stored</p>",
        published_at=datetime(2031, 1, 1, tzinfo=UTC),
        created_at=original_fetch,
        updated_at=original_fetch,
    )
    mcp_db_session.add(stored)
    await mcp_db_session.commit()

    feed_id = feed.id
    before = datetime.now(UTC)
    with (
        patch(
            "glean_worker.tasks.feed_fetcher.fetch_feed",
            new=AsyncMock(return_value=(b"<rss/>", {})),
        ),
        patch(
            "glean_worker.tasks.feed_fetcher.parse_feed",
            new=AsyncMock(return_value=_parsed_feed()),
        ),
        patch(
            "glean_worker.tasks.feed_fetcher._should_embed_entries",
            new=AsyncMock(return_value=False),
        ),
    ):
        result = await fetch_feed_task({}, feed.id)
    after = datetime.now(UTC)

    assert result["status"] == "success"
    assert result["new_entries"] == 3

    fresh = async_sessionmaker(
        bind=mcp_db_session.bind,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with fresh() as session:
        rows = (
            (await session.execute(select(Entry).where(Entry.feed_id == feed_id))).scalars().all()
        )
        by_guid = {row.guid: row for row in rows}
        stored_feed = await session.get(Feed, feed_id)

        assert by_guid["kept-past"].published_at == datetime(2026, 2, 1, 8, 0, tzinfo=UTC)
        assert before <= by_guid["replaced-future"].published_at <= after
        assert before <= by_guid["replaced-missing"].published_at <= after
        assert by_guid["already-stored"].published_at == original_fetch
        assert stored_feed is not None
        assert stored_feed.last_entry_at == by_guid["replaced-future"].published_at

        await session.delete(stored_feed)
        await session.commit()


@pytest.mark.asyncio
async def test_timeline_displays_fetch_time_for_legacy_abnormal_dates(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_feed: Feed,
    test_subscription: object,
) -> None:
    """Rows not yet refreshed still show the fetch time instead of a future date."""
    fetched_at = datetime.now(UTC) - timedelta(days=2)
    past = datetime(2026, 2, 1, 8, 0, tzinfo=UTC)
    db_session.add_all(
        [
            Entry(
                feed_id=test_feed.id,
                guid="legacy-past",
                url="https://example.com/legacy/past",
                title="Legacy past",
                published_at=past,
                created_at=fetched_at,
                updated_at=fetched_at,
            ),
            Entry(
                feed_id=test_feed.id,
                guid="legacy-future",
                url="https://example.com/legacy/future",
                title="Legacy future",
                published_at=datetime(2030, 6, 1, tzinfo=UTC),
                created_at=fetched_at,
                updated_at=fetched_at,
            ),
            Entry(
                feed_id=test_feed.id,
                guid="legacy-missing",
                url="https://example.com/legacy/missing",
                title="Legacy missing",
                published_at=None,
                created_at=fetched_at,
                updated_at=fetched_at,
            ),
        ]
    )
    await db_session.commit()

    response = await client.get("/api/entries?view=timeline", headers=auth_headers)

    assert response.status_code == 200
    by_title = {item["title"]: item for item in response.json()["items"]}
    assert by_title["Legacy past"]["published_at"].startswith("2026-02-01T08:00:00")
    assert by_title["Legacy future"]["published_at"] == by_title["Legacy future"]["created_at"]
    assert by_title["Legacy missing"]["published_at"] == by_title["Legacy missing"]["created_at"]
    assert not by_title["Legacy future"]["published_at"].startswith("2030")
    # Legacy nulls and far-future values still use the indexed column, so they
    # sort ahead of a real older date until the next fetch rewrites them.
    titles = [item["title"] for item in response.json()["items"]]
    assert titles.index("Legacy past") > titles.index("Legacy future")
    assert titles.index("Legacy past") > titles.index("Legacy missing")

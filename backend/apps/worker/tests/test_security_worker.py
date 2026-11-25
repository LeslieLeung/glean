"""Security regression tests for background workers (feed_fetcher and bookmark_metadata)."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from glean_database.models import Bookmark, Entry, Feed, FeedStatus, User
from glean_rss import ParsedEntry
from glean_worker.tasks.bookmark_metadata import fetch_bookmark_metadata_task
from glean_worker.tasks.feed_fetcher import (
    MAX_ENTRIES_PER_FETCH,
    MAX_FULLTEXT_PER_FETCH,
    fetch_feed_task,
)


def _session_ctx_for(db_session: AsyncSession):
    @asynccontextmanager
    async def _ctx():
        yield db_session
        await db_session.flush()

    return _ctx


@pytest.mark.asyncio
class TestFeedFetcherSecurity:
    """Tests for worker CancelledError backoff and per-fetch caps."""

    async def test_cancelled_error_rolls_back_sets_backoff_and_reraises(
        self, db_session: AsyncSession
    ) -> None:
        feed = Feed(
            id=str(uuid4()),
            url="https://example.com/slow.xml",
            title="Slow Feed",
            status=FeedStatus.ACTIVE,
            error_count=9,
        )
        db_session.add(feed)
        await db_session.commit()

        with (
            patch(
                "glean_worker.tasks.feed_fetcher.get_session_context", _session_ctx_for(db_session)
            ),
            patch(
                "glean_worker.tasks.feed_fetcher.fetch_feed",
                AsyncMock(side_effect=asyncio.CancelledError()),
            ),
            pytest.raises(asyncio.CancelledError),
        ):
            await fetch_feed_task({"redis": AsyncMock()}, feed.id)

        await db_session.refresh(feed)
        assert feed.error_count == 10
        assert feed.status == FeedStatus.ERROR
        assert feed.next_fetch_at is not None
        assert "cancelled" in (feed.fetch_error_message or "").lower()

    async def test_caps_entries_and_fulltext_extractions_per_fetch(
        self, db_session: AsyncSession
    ) -> None:
        feed = Feed(
            id=str(uuid4()),
            url="https://example.com/flood.xml",
            title="Flood Feed",
            status=FeedStatus.ACTIVE,
        )
        db_session.add(feed)
        await db_session.commit()

        raw_entries = [
            {
                "id": f"guid-{i}",
                "link": f"https://example.com/post-{i}",
                "title": f"Post {i}",
                "summary": "<p>short</p>",
            }
            for i in range(MAX_ENTRIES_PER_FETCH + 25)
        ]
        parsed_feed = SimpleNamespace(
            title="Flood Feed",
            description="desc",
            site_url="https://example.com",
            language="en",
            icon_url=None,
            entries=[ParsedEntry(item) for item in raw_entries],
        )

        mock_fulltext = AsyncMock(return_value="<p>Full text</p>")
        with (
            patch(
                "glean_worker.tasks.feed_fetcher.get_session_context", _session_ctx_for(db_session)
            ),
            patch(
                "glean_worker.tasks.feed_fetcher._should_embed_entries",
                AsyncMock(return_value=False),
            ),
            patch(
                "glean_worker.tasks.feed_fetcher.fetch_feed",
                AsyncMock(return_value=("<rss/>", {})),
            ),
            patch(
                "glean_worker.tasks.feed_fetcher.parse_feed", AsyncMock(return_value=parsed_feed)
            ),
            patch("glean_worker.tasks.feed_fetcher.fetch_and_extract_fulltext", mock_fulltext),
        ):
            result = await fetch_feed_task({"redis": AsyncMock()}, feed.id)

        assert result["new_entries"] == MAX_ENTRIES_PER_FETCH
        assert mock_fulltext.await_count == MAX_FULLTEXT_PER_FETCH

        entry_count = await db_session.scalar(
            select(func.count()).select_from(Entry).where(Entry.feed_id == feed.id)
        )
        assert entry_count == MAX_ENTRIES_PER_FETCH


@pytest.mark.asyncio
class TestBookmarkMetadataWorkerSecurity:
    """Tests for bookmark metadata SSRF, size, and MIME rejection status transitions."""

    async def _create_bookmark(self, db_session: AsyncSession, url: str) -> Bookmark:
        user = User(
            id=str(uuid4()),
            email=f"bm-{uuid4().hex[:6]}@example.com",
            name="BM User",
            password_hash="x",
            primary_auth_provider="local",
            provider_user_id=f"bm-{uuid4().hex[:6]}",
            is_active=True,
            is_verified=True,
        )
        db_session.add(user)
        await db_session.flush()
        bm = Bookmark(
            id=str(uuid4()),
            user_id=user.id,
            url=url,
            title="Pending",
            snapshot_status="pending",
        )
        db_session.add(bm)
        await db_session.commit()
        return bm

    async def test_rejects_ssrf_url_and_marks_failed(self, db_session: AsyncSession) -> None:
        bm = await self._create_bookmark(db_session, "http://127.0.0.1/secret")

        with patch(
            "glean_worker.tasks.bookmark_metadata.get_session_context",
            _session_ctx_for(db_session),
        ):
            result = await fetch_bookmark_metadata_task({}, bm.id)

        assert result["status"] == "error"
        await db_session.refresh(bm)
        assert bm.snapshot_status == "failed"

    async def test_rejects_non_html_content_type_and_marks_failed(
        self, db_session: AsyncSession
    ) -> None:
        bm = await self._create_bookmark(db_session, "https://example.com/archive.zip")

        mock_client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _req: httpx.Response(
                    200,
                    headers={"content-type": "application/zip"},
                    content=b"PK\x03\x04binary",
                )
            )
        )

        with (
            patch(
                "glean_worker.tasks.bookmark_metadata.get_session_context",
                _session_ctx_for(db_session),
            ),
            patch(
                "glean_worker.tasks.bookmark_metadata.safe_async_client",
                return_value=mock_client,
            ),
        ):
            result = await fetch_bookmark_metadata_task({}, bm.id)

        assert result["status"] == "error"
        await db_session.refresh(bm)
        assert bm.snapshot_status == "failed"

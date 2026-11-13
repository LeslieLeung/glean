"""Metadata jobs preserve edits and surface fetch failures."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import httpx
import pytest

from glean_database.models import Bookmark, User
from glean_worker.tasks import bookmark_metadata


@pytest.mark.parametrize("result", ["success", "network", "non_html"])
async def test_fetch_status_and_edits_in_flight(db_session, monkeypatch, result):
    user = User()
    db_session.add(user)
    await db_session.flush()
    bookmark = Bookmark(
        user_id=user.id, url="https://example.org/test", title="https://example.org/test"
    )
    db_session.add(bookmark)
    await db_session.commit()

    @asynccontextmanager
    async def session_context():
        yield db_session
        await db_session.commit()

    async def get(url):
        # Simulate a user edit after the job began fetching.
        bookmark.title = "My edited title"
        bookmark.title_edited = True
        bookmark.excerpt = ""
        bookmark.excerpt_edited = True
        await db_session.commit()
        if result == "network":
            raise httpx.ConnectError("offline")
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            headers={"content-type": "application/pdf" if result == "non_html" else "text/html"},
            text='<title>Remote title</title><meta name="description" content="Remote summary"><p>Body</p>',
        )

    @asynccontextmanager
    async def http_client(**kwargs):
        yield type("Client", (), {"get": staticmethod(get)})()

    monkeypatch.setattr(bookmark_metadata, "get_session_context", session_context)
    monkeypatch.setattr(bookmark_metadata, "safe_async_client", http_client)
    monkeypatch.setattr(
        bookmark_metadata, "extract_fulltext", AsyncMock(return_value="<p>Saved body</p>")
    )
    await bookmark_metadata.fetch_bookmark_metadata_task({}, bookmark.id)
    await db_session.refresh(bookmark)
    assert bookmark.title == "My edited title"
    assert bookmark.excerpt == ""
    assert bookmark.snapshot_status == ("done" if result == "success" else "failed")
    assert bookmark.content == ("<p>Saved body</p>" if result == "success" else None)

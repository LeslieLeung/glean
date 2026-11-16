"""Regression tests for entry-backed bookmark authorization."""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from glean_database.models import Bookmark, Entry, Feed, Subscription, User


@pytest.fixture
async def private_entry(db_session: AsyncSession, test_feed: Feed) -> Entry:
    """Create an entry in a feed subscribed to only by another user."""
    owner = User(email="private-feed-owner@example.com")
    db_session.add(owner)
    await db_session.flush()
    entry = Entry(
        feed_id=test_feed.id,
        url="https://internal.example/private-article",
        title="Private entry title",
        content="<p>Private entry content</p>",
        summary="<p>Private entry summary</p>",
    )
    db_session.add_all([entry, Subscription(user_id=owner.id, feed_id=test_feed.id)])
    await db_session.commit()
    return entry


@pytest.mark.asyncio
@pytest.mark.parametrize("supply_metadata", [False, True])
async def test_create_bookmark_rejects_unsubscribed_entry(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
    private_entry: Entry,
    test_mock_redis,
    supply_metadata: bool,
) -> None:
    """Neither another user's subscription nor a different feed grants access."""
    other_feed = Feed(url="https://example.com/other-feed.xml", title="Other feed")
    db_session.add(other_feed)
    await db_session.flush()
    db_session.add(Subscription(user_id=test_user.id, feed_id=other_feed.id))
    await db_session.commit()

    entry_response = await client.get(f"/api/entries/{private_entry.id}", headers=auth_headers)
    assert entry_response.status_code == 404
    assert entry_response.json()["detail"] == "Not subscribed to this feed"

    payload = {"entry_id": private_entry.id}
    if supply_metadata:
        payload.update(
            url="https://example.com/article", title="Custom title", excerpt="Custom excerpt"
        )
    response = await client.post("/api/bookmarks", json=payload, headers=auth_headers)

    assert response.status_code == 400
    assert response.json() == {"detail": "Not subscribed to this feed"}
    count = await db_session.scalar(
        select(func.count()).select_from(Bookmark).where(Bookmark.user_id == test_user.id)
    )
    assert count == 0
    assert test_mock_redis.enqueued_jobs == []


@pytest.mark.asyncio
@pytest.mark.parametrize("use_summary", [False, True])
async def test_create_bookmark_from_subscribed_entry(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_user: User,
    private_entry: Entry,
    use_summary: bool,
) -> None:
    """Subscribers can save entry metadata and repeated requests reuse the bookmark."""
    db_session.add(Subscription(user_id=test_user.id, feed_id=private_entry.feed_id))
    if use_summary:
        private_entry.content = None
    await db_session.commit()

    response = await client.post(
        "/api/bookmarks", json={"entry_id": private_entry.id}, headers=auth_headers
    )
    assert response.status_code == 201
    bookmark = response.json()
    assert bookmark["entry_id"] == private_entry.id
    assert bookmark["user_id"] == test_user.id
    assert bookmark["title"] == private_entry.title
    assert bookmark["excerpt"] == (
        "Private entry summary" if use_summary else "Private entry content"
    )

    saved = await client.get(f"/api/bookmarks/{bookmark['id']}", headers=auth_headers)
    assert saved.status_code == 200
    assert saved.json() == bookmark

    duplicate = await client.post(
        "/api/bookmarks", json={"entry_id": private_entry.id}, headers=auth_headers
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == bookmark["id"]
    count = await db_session.scalar(
        select(func.count()).select_from(Bookmark).where(Bookmark.user_id == test_user.id)
    )
    assert count == 1


@pytest.mark.asyncio
async def test_create_bookmark_rejects_nonexistent_entry(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/bookmarks", json={"entry_id": str(uuid4())}, headers=auth_headers
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Entry not found"}

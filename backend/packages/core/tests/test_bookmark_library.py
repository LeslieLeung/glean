"""Bookmark library behavior, persistence and ownership boundaries."""

from typing import Any, cast

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core.schemas.bookmark import BookmarkCreate, BookmarkUpdate
from glean_core.services.bookmark_service import BookmarkService
from glean_database.models import Entry, Feed, Folder, Tag, User


class UndoCache:
    def __init__(self):
        self.values: dict[str, str] = {}

    async def setex(self, key: str, ttl: int, value: str):
        assert ttl == 30
        self.values[key] = value

    async def get(self, key: str):
        return self.values.get(key)

    async def delete(self, key: str):
        self.values.pop(key, None)

    async def sadd(self, *args: Any):
        pass

    async def enqueue_job(self, *args: Any, **kwargs: Any):
        pass


async def setup_library(session: AsyncSession):
    user, other = User(), User()
    feed = Feed(url="https://example.org/feed", title="Reference source")
    session.add_all([user, other, feed])
    await session.flush()
    entry = Entry(
        feed_id=feed.id,
        url="https://example.org/article",
        title="Article",
        content="<p>Preserved body</p>",
        summary="Useful summary",
    )
    session.add(entry)
    await session.commit()
    return user, other, feed, entry


async def test_snapshot_survives_source_deletion(db_session: AsyncSession):
    user, _, feed, entry = await setup_library(db_session)
    service = BookmarkService(db_session)
    saved, needs_fetch = await service.create_bookmark(user.id, BookmarkCreate(entry_id=entry.id))
    assert not needs_fetch
    assert saved.url == entry.url
    assert saved.content == entry.content
    assert saved.source_type == "rss"
    await db_session.execute(delete(Feed).where(Feed.id == feed.id))
    await db_session.commit()
    db_session.expire_all()
    restored = await service.get_bookmark(saved.id, saved.user_id)
    assert restored.entry_id is None
    assert restored.content == "<p>Preserved body</p>"
    assert restored.source_name == "Reference source"


@pytest.mark.parametrize("external_first", [True, False])
async def test_duplicates_preserve_edits_and_time(db_session: AsyncSession, external_first: bool):
    user, _, _, entry = await setup_library(db_session)
    service = BookmarkService(db_session)
    requests = [BookmarkCreate(url=entry.url, title="My title"), BookmarkCreate(entry_id=entry.id)]
    if not external_first:
        requests.reverse()
    first, _ = await service.create_bookmark(user.id, requests[0])
    await service.update_bookmark(first.id, user.id, BookmarkUpdate(title="Edited", excerpt=""))
    second, fetch = await service.create_bookmark(user.id, requests[1])
    assert second.already_exists and not fetch
    assert second.id == first.id
    assert second.title == "Edited"
    assert second.excerpt == ""
    assert second.created_at == first.created_at
    assert (await service.get_bookmarks(user.id)).total == 1


async def test_folder_descendants_unfiled_and_combined_search(db_session: AsyncSession):
    user, other, _, entry = await setup_library(db_session)
    parent = Folder(user_id=user.id, name="Project", type="bookmark")
    tag = Tag(user_id=user.id, name="Topic")
    db_session.add_all([parent, tag])
    await db_session.flush()
    child = Folder(user_id=user.id, name="Child", type="bookmark", parent_id=parent.id)
    db_session.add(child)
    await db_session.commit()
    service = BookmarkService(db_session)
    first, _ = await service.create_bookmark(
        user.id,
        BookmarkCreate(entry_id=entry.id, folder_ids=[parent.id, child.id], tag_ids=[tag.id]),
    )
    second, _ = await service.create_bookmark(
        user.id,
        BookmarkCreate(
            url="https://external.org/doc", excerpt="distinctive summary", tag_ids=[tag.id]
        ),
    )
    assert (await service.get_bookmarks(user.id, folder_id=parent.id)).total == 1
    assert (await service.get_bookmarks(other.id, folder_id=parent.id)).total == 0
    assert (await service.get_bookmarks(user.id, unfiled=True)).items[0].id == second.id
    assert (
        await service.get_bookmarks(
            user.id, search="distinctive", tag_ids=[tag.id], source_type="external"
        )
    ).total == 1
    assert (await service.get_bookmarks(user.id, search="Reference source")).items[0].id == first.id
    assert (await service.get_bookmarks(user.id, search="external.org")).total == 1
    assert (await service.get_bookmarks(user.id, search="%not a wildcard%")).total == 0
    await db_session.delete(parent)
    await db_session.commit()
    assert (await service.get_bookmarks(user.id)).total == 2


async def test_undo_restores_exact_data_and_checks_owner(db_session: AsyncSession):
    user, other, _, entry = await setup_library(db_session)
    tag = Tag(user_id=user.id, name="Keep")
    folder = Folder(user_id=user.id, name="Keep", type="bookmark")
    db_session.add_all([tag, folder])
    await db_session.commit()
    service = BookmarkService(db_session, cast(Any, UndoCache()))
    saved, _ = await service.create_bookmark(
        user.id, BookmarkCreate(entry_id=entry.id, tag_ids=[tag.id], folder_ids=[folder.id])
    )
    await service.delete_bookmark(saved.id, user.id)
    assert (await service.get_bookmarks(user.id)).total == 0
    with pytest.raises(ValueError):
        await service.restore_bookmark(saved.id, other.id)
    restored = await service.restore_bookmark(saved.id, user.id)
    assert restored.id == saved.id
    assert restored.created_at == saved.created_at
    assert restored.content == saved.content
    assert restored.tags == saved.tags
    assert restored.folders == saved.folders
    assert (await service.restore_bookmark(saved.id, user.id)).id == saved.id


async def test_queue_failure_retains_bookmark_for_retry(db_session: AsyncSession):
    user, _, _, _ = await setup_library(db_session)
    service = BookmarkService(db_session)
    saved, fetch = await service.create_bookmark(
        user.id,
        BookmarkCreate(url="https://example.org/retry", title="Custom", excerpt="Custom summary"),
    )
    assert fetch
    result = await service.retry_content(saved.id, user.id)
    assert result.snapshot_status == "failed"
    assert result.title == "Custom"


@pytest.mark.parametrize(
    "url",
    ["javascript:alert(1)", "file:///etc/passwd", "https://user:password@example.org", "not a URL"],
)
def test_invalid_link_rejected(url: str):
    with pytest.raises(ValueError):
        BookmarkCreate(url=url)


async def test_bookmark_api_retry_restore_and_filters(client, auth_headers, test_mock_redis):
    response = await client.post(
        "/api/bookmarks",
        headers=auth_headers,
        json={
            "url": "https://example.org/api",
            "title": "API title",
            "excerpt": "searchable summary",
        },
    )
    assert response.status_code == 201, response.text
    bookmark_id = response.json()["id"]
    duplicate = await client.post(
        "/api/bookmarks", headers=auth_headers, json={"url": "https://example.org/api"}
    )
    assert duplicate.json()["already_exists"] is True
    result = await client.get(
        "/api/bookmarks?unfiled=true&source_type=external&search=searchable", headers=auth_headers
    )
    assert result.json()["total"] == 1
    result = await client.post(f"/api/bookmarks/{bookmark_id}/retry", headers=auth_headers)
    assert result.status_code == 200
    assert result.json()["snapshot_status"] == "pending"
    assert test_mock_redis.enqueued_jobs[-1][0] == "fetch_bookmark_metadata_task"
    assert (
        await client.delete(f"/api/bookmarks/{bookmark_id}", headers=auth_headers)
    ).status_code == 204
    result = await client.post(f"/api/bookmarks/{bookmark_id}/restore", headers=auth_headers)
    assert result.status_code == 200
    assert result.json()["title"] == "API title"
    assert (
        await client.get("/api/bookmarks?sort=user_id", headers=auth_headers)
    ).status_code == 422


async def test_external_bookmark_state_is_shared_by_matching_rss_articles(db_session):
    from glean_core.services.entry_service import EntryService
    from glean_database.models import Subscription

    user, _, feed, entry = await setup_library(db_session)
    duplicate_entry = Entry(feed_id=feed.id, url=entry.url, title="Same address")
    db_session.add_all([duplicate_entry, Subscription(user_id=user.id, feed_id=feed.id)])
    await db_session.commit()
    bookmarks = BookmarkService(db_session)
    saved, _ = await bookmarks.create_bookmark(user.id, BookmarkCreate(url=entry.url))
    entries = EntryService(db_session)
    assert (await entries.get_entry(entry.id, user.id)).bookmark_id == saved.id
    assert (await entries.get_entry(duplicate_entry.id, user.id)).is_bookmarked
    listing = await entries.get_entries(user.id)
    assert all(item.bookmark_id == saved.id for item in listing.items)
    await bookmarks.delete_bookmark(saved.id, user.id)
    assert not (await entries.get_entry(entry.id, user.id)).is_bookmarked

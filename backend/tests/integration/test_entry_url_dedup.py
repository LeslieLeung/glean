"""Cross-feed URL deduplication with real SQL, pagination and user state."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from glean_core.schemas import UpdateEntryStateRequest
from glean_core.services.entry_service import EntryService
from glean_core.services.feed_service import FeedService
from glean_database.models import Bookmark, Entry, Feed, Folder, Subscription, User, UserEntry


@pytest_asyncio.fixture
async def duplicate_articles(db_session, test_user):
    now = datetime.now(UTC)
    feeds = [Feed(url=f"https://example.com/feed-{i}", title=f"Feed {i}") for i in range(3)]
    folder = Folder(user_id=test_user.id, name="Aggregation", type="feed")
    db_session.add_all([*feeds, folder])
    await db_session.flush()
    db_session.add_all(
        Subscription(
            user_id=test_user.id,
            feed_id=feed.id,
            folder_id=folder.id if i == 1 else None,
            created_at=now + timedelta(seconds=i),
        )
        for i, feed in enumerate(feeds[:2])
    )
    entries = [
        Entry(
            feed_id=feed.id,
            url="https://example.com/shared",
            title=f"Shared from {i}",
            guid=f"different-guid-{i}",
            published_at=now,
        )
        for i, feed in enumerate(feeds)
    ]
    entries.append(
        Entry(
            feed_id=feeds[1].id,
            url="https://example.com/unique",
            title="Unique",
            guid="unique",
            published_at=now - timedelta(hours=1),
        )
    )
    db_session.add_all(entries)
    await db_session.commit()
    return feeds, entries, folder


@pytest.mark.parametrize("view", ["timeline", "smart"])
async def test_dedup_before_count_pagination_and_scoring(
    db_session, test_user, duplicate_articles, view
):
    feeds, entries, folder = duplicate_articles
    service = EntryService(db_session)
    scorer = AsyncMock()
    scorer.batch_calculate_scores.side_effect = lambda _, items: {e.id: 50.0 for e in items}
    first = await service.get_entries(test_user.id, per_page=1, view=view, score_service=scorer)
    second = await service.get_entries(
        test_user.id, page=2, per_page=1, view=view, score_service=scorer
    )
    assert first.total == second.total == 2
    assert first.total_pages == 2
    assert first.items[0].id == entries[0].id
    assert second.items[0].id == entries[3].id
    if view == "smart":
        assert all(len(call.args[1]) == 2 for call in scorer.batch_calculate_scores.call_args_list)

    scoped = await service.get_entries(test_user.id, feed_id=feeds[1].id)
    assert {item.id for item in scoped.items} == {entries[1].id, entries[3].id}
    scoped = await service.get_entries(test_user.id, folder_id=folder.id)
    assert {item.id for item in scoped.items} == {entries[1].id, entries[3].id}


async def test_url_state_shared_across_sources_and_future_copies(
    db_session, test_user, duplicate_articles
):
    feeds, entries, _ = duplicate_articles
    service = EntryService(db_session)
    await service.update_entry_state(
        entries[1].id,
        test_user.id,
        UpdateEntryStateRequest(is_read=True, is_liked=True, read_later=True),
    )
    original = await service.get_entry(entries[0].id, test_user.id)
    assert original.is_read and original.is_liked and original.read_later
    unread = await service.get_entries(test_user.id, is_read=False)
    assert [item.id for item in unread.items] == [entries[3].id]
    liked = await service.get_entries(test_user.id, is_liked=True)
    assert [item.id for item in liked.items] == [entries[0].id]
    subscriptions = await FeedService(db_session).get_user_subscriptions(test_user.id)
    assert {sub.feed_id: sub.unread_count for sub in subscriptions} == {
        feeds[0].id: 0,
        feeds[1].id: 1,
    }

    # A new subscription/copy must inherit the URL's state without a backfill.
    late_copy = Entry(
        feed_id=feeds[2].id, url=entries[0].url, title="Fetched later", guid="late-copy"
    )
    db_session.add(late_copy)
    db_session.add(Subscription(user_id=test_user.id, feed_id=feeds[2].id))
    await db_session.commit()
    copy = await service.get_entry(late_copy.id, test_user.id)
    assert copy.is_read and copy.is_liked and copy.read_later
    await service.update_entry_state(
        entries[2].id, test_user.id, UpdateEntryStateRequest(is_read=False)
    )
    assert not (await service.get_entry(entries[0].id, test_user.id)).is_read
    assert (await service.get_entry(entries[0].id, test_user.id)).is_liked


async def test_url_state_and_dedup_are_user_scoped(db_session, test_user, duplicate_articles):
    feeds, entries, _ = duplicate_articles
    other = User(email="other-dedup@example.com")
    db_session.add(other)
    await db_session.flush()
    db_session.add(Subscription(user_id=other.id, feed_id=feeds[1].id))
    await db_session.commit()
    service = EntryService(db_session)
    await service.update_entry_state(
        entries[0].id, test_user.id, UpdateEntryStateRequest(is_read=True)
    )
    result = await service.get_entries(other.id, is_read=False)
    assert result.total == 2
    assert result.items[0].id == entries[1].id
    assert all(not item.is_read for item in result.items)


async def test_bulk_read_and_legacy_states(db_session, test_user, duplicate_articles):
    feeds, entries, folder = duplicate_articles
    now = datetime.now(UTC)
    db_session.add_all(
        [
            UserEntry(
                user_id=test_user.id,
                entry_id=entries[0].id,
                is_read=True,
                updated_at=now - timedelta(days=1),
            ),
            UserEntry(
                user_id=test_user.id,
                entry_id=entries[1].id,
                is_read=False,
                updated_at=now - timedelta(hours=1),
            ),
        ]
    )
    await db_session.commit()
    service = EntryService(db_session)
    assert (await service.get_entries(test_user.id, is_read=False)).total == 2
    await service.mark_all_read(test_user.id, folder_id=folder.id)
    assert (await service.get_entries(test_user.id, is_read=False)).total == 0
    assert (await service.get_entry(entries[0].id, test_user.id)).is_read


async def test_bookmark_on_duplicate_is_visible(db_session, test_user, duplicate_articles):
    _, entries, _ = duplicate_articles
    bookmark = Bookmark(
        user_id=test_user.id, entry_id=entries[1].id, url=entries[1].url, title="Saved copy"
    )
    db_session.add(bookmark)
    await db_session.commit()
    service = EntryService(db_session)
    result = await service.get_entries(test_user.id)
    assert result.items[0].is_bookmarked
    assert result.items[0].bookmark_id == bookmark.id
    assert (await service.get_entry(entries[0].id, test_user.id)).bookmark_id == bookmark.id


async def test_exact_url_identity_not_title_or_guid(db_session, test_user, duplicate_articles):
    feeds, entries, _ = duplicate_articles
    db_session.add_all(
        [
            Entry(
                feed_id=feeds[0].id,
                url=entries[0].url,
                title="Different title",
                guid="same-url-new-guid",
            ),
            Entry(
                feed_id=feeds[0].id,
                url=entries[0].url + "?page=2",
                title=entries[0].title,
                guid="different-page",
            ),
        ]
    )
    await db_session.commit()
    result = await EntryService(db_session).get_entries(test_user.id)
    assert result.total == 3
    assert len({item.url for item in result.items}) == 3

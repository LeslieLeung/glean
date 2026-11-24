"""Smart ranking regressions against the entry service and its real SQL queries."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from glean_core.services.entry_rank_snapshot import SmartCursorExpiredError
from glean_core.services.entry_service import EntryService
from glean_database.models import Entry, Feed, Subscription, UserEntry


@pytest.fixture
async def subscribed_feed(db_session, test_user):
    async def subscribe(name):
        feed = Feed(url=f"https://example.com/{name}.xml", title=name)
        db_session.add(feed)
        await db_session.flush()
        db_session.add(Subscription(user_id=test_user.id, feed_id=feed.id))
        await db_session.flush()
        return feed

    return subscribe


def _entry(feed, now, name, *, age_hours=0, title=None, summary=None):
    return Entry(
        feed_id=feed.id,
        url=f"https://example.com/{name}",
        guid=name,
        title=title or name,
        summary=summary,
        published_at=now - timedelta(hours=age_hours),
    )


async def test_smart_pagination_keeps_rank_when_read_state_changes(
    db_session, test_user, subscribed_feed
) -> None:
    now = datetime.now(UTC)
    feed = await subscribed_feed("feed")
    entries = [_entry(feed, now, f"item-{i}", age_hours=i) for i in range(120)]
    db_session.add_all(entries)
    await db_session.flush()
    redis = AsyncMock()
    snapshots = {}

    async def store_snapshot(key, _ttl, value):
        snapshots[key] = value

    redis.setex.side_effect = store_snapshot
    redis.get.side_effect = snapshots.get
    service = EntryService(db_session, redis)
    filters = {
        "user_id": test_user.id,
        "per_page": 20,
        "view": "smart",
        "is_read": False,
        "use_cursor": True,
    }
    first = await service.get_entries(**filters)
    assert [item.id for item in first.items] == [entry.id for entry in entries[:20]]
    assert first.items[0].preference_score > first.items[-1].preference_score
    assert first.next_cursor

    # One article in the first page and another at the next page boundary are now read.
    db_session.add_all(
        [
            UserEntry(user_id=test_user.id, entry_id=entries[index].id, is_read=True)
            for index in (0, 20)
        ]
    )
    await db_session.flush()
    second = await service.get_entries(**filters, cursor=first.next_cursor)
    assert [item.id for item in second.items] == [entry.id for entry in entries[21:41]]

    page = second
    for _ in range(4):
        assert page.next_cursor
        page = await service.get_entries(**filters, cursor=page.next_cursor)
    assert page.items[-1].id == entries[-1].id
    assert page.next_cursor is None
    with pytest.raises(SmartCursorExpiredError):
        await service.get_entries(**(filters | {"feed_id": feed.id}), cursor=first.next_cursor)
    snapshots.clear()
    with pytest.raises(SmartCursorExpiredError):
        await service.get_entries(**filters, cursor=first.next_cursor)


async def test_text_feedback_reorders_cross_feed_without_vectors(
    db_session, test_user, subscribed_feed
) -> None:
    now = datetime.now(UTC)
    source = await subscribed_feed("source")
    destination = await subscribed_feed("destination")
    sample = _entry(source, now, "sample", title="ESP-IDF provisioning Wi-Fi")
    related = _entry(destination, now, "related", title="ESP-IDF provisioning Wi-Fi", age_hours=24)
    unrelated = _entry(destination, now, "unrelated", title="Unrelated database news", age_hours=23)
    old = _entry(destination, now, "old", age_hours=24 * 30)
    db_session.add_all([sample, related, unrelated, old])
    await db_session.flush()
    service = EntryService(db_session)
    before = await service.get_entries(test_user.id, feed_id=destination.id, view="smart")
    assert before.items[0].id == unrelated.id

    reaction = UserEntry(user_id=test_user.id, entry_id=sample.id, is_liked=True, is_read=True)
    db_session.add(reaction)
    await db_session.flush()
    scoped = await service.get_entries(test_user.id, feed_id=destination.id, view="smart")
    assert [entry.id for entry in scoped.items] == [related.id, unrelated.id, old.id]
    timeline = await service.get_entries(
        test_user.id, feed_id=destination.id, include_score=True, per_page=2
    )
    assert [entry.id for entry in timeline.items] == [unrelated.id, related.id]
    assert timeline.items[1].preference_score == pytest.approx(
        scoped.items[0].preference_score, abs=0.01
    )

    global_smart = await service.get_entries(test_user.id, view="smart", global_smart=True)
    assert [entry.id for entry in global_smart.items] == [related.id, unrelated.id]
    reaction.is_liked = None
    await db_session.flush()
    after = await service.get_entries(test_user.id, feed_id=destination.id, view="smart")
    assert after.items[0].id == unrelated.id

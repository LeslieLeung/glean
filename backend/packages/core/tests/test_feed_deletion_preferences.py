"""Feed deletion must invalidate signals owned by users without a subscription."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core.services import AdminService, FeedService
from glean_database.models import Bookmark, Entry, Feed, Subscription, User, UserEntry


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["admin", "admin_batch", "unsubscribe", "unsubscribe_batch"])
async def test_feed_deletion_dirties_bookmark_and_reaction_owners(
    db_session: AsyncSession, mode: str
) -> None:
    subscriber, bookmark_owner, reaction_owner = User(), User(), User()
    feed = Feed(url="https://example.com/deleted-history")
    db_session.add_all([subscriber, bookmark_owner, reaction_owner, feed])
    await db_session.flush()
    entry = Entry(feed_id=feed.id, url="https://example.com/history-entry", title="History")
    subscription = Subscription(user_id=subscriber.id, feed_id=feed.id)
    db_session.add_all([entry, subscription])
    await db_session.flush()
    bookmark = Bookmark(
        user_id=bookmark_owner.id,
        entry_id=entry.id,
        url=entry.url,
        title=entry.title,
    )
    db_session.add_all(
        [bookmark, UserEntry(user_id=reaction_owner.id, entry_id=entry.id, is_liked=True)]
    )
    await db_session.commit()
    owner_ids = [subscriber.id, bookmark_owner.id, reaction_owner.id]
    bookmark_id = bookmark.id

    if mode == "admin":
        await AdminService(db_session).delete_feed(feed.id)
    elif mode == "admin_batch":
        await AdminService(db_session).batch_feed_operation("delete", [feed.id])
    elif mode == "unsubscribe":
        await FeedService(db_session).delete_subscription(subscription.id, subscriber.id)
    else:
        await FeedService(db_session).batch_delete_subscriptions([subscription.id], subscriber.id)

    revisions = await db_session.execute(
        select(User.preference_revision).where(User.id.in_(owner_ids))
    )
    assert all(revision > 0 for revision in revisions.scalars().all())
    assert (
        await db_session.scalar(select(Bookmark.entry_id).where(Bookmark.id == bookmark_id)) is None
    )

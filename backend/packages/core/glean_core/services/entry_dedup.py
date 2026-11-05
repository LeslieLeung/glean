"""URL-based article identity while preserving each feed's entries."""

from sqlalchemy import select
from sqlalchemy.orm import InstrumentedAttribute, aliased
from sqlalchemy.sql.selectable import ScalarSelect

from glean_database.models import Entry, UserEntry


def url_user_entry_id(
    user_id: str, url: str | InstrumentedAttribute[str] = Entry.url
) -> ScalarSelect[str]:
    """Resolve the user's latest state for a URL, including later-fetched copies.

    Legacy copies can have different states. The most recently updated state
    wins deterministically; all subsequent interactions update that same row.
    """
    source = aliased(Entry)
    state = aliased(UserEntry)
    return (
        select(state.id)
        .join(source, source.id == state.entry_id)
        .where(state.user_id == user_id, source.url == url)
        .order_by(state.updated_at.desc(), state.created_at.desc(), state.id)
        .correlate(Entry)
        .limit(1)
        .scalar_subquery()
    )

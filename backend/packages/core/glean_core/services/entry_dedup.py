"""URL-based article identity while preserving each feed's entries."""

from sqlalchemy import case, func, or_, select, tuple_
from sqlalchemy.orm import InstrumentedAttribute, aliased
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import ScalarSelect

from glean_database.models import Entry, UserEntry


def linkless_entry_id() -> ColumnElement[str | None]:
    """Distinguish entries with an empty URL when grouping by article identity."""
    return case((Entry.url == "", Entry.id))


def count_distinct_articles() -> ColumnElement[int]:
    """Count non-empty URLs once and linkless entries individually."""
    return func.count(func.distinct(tuple_(Entry.url, linkless_entry_id())))


def url_user_entry_id(
    user_id: str,
    url: str | InstrumentedAttribute[str] = Entry.url,
    entry_id: str | InstrumentedAttribute[str] = Entry.id,
) -> ScalarSelect[str]:
    """Resolve the user's latest state for a URL, including later-fetched copies.

    Entries without a URL use their own state. When legacy copies have different
    states, the most recently updated row supplies the shared state and receives
    subsequent updates.
    """
    source = aliased(Entry)
    state = aliased(UserEntry)
    return (
        select(state.id)
        .join(source, source.id == state.entry_id)
        .where(
            state.user_id == user_id,
            source.url == url,
            or_(source.url != "", state.entry_id == entry_id),
        )
        .order_by(state.updated_at.desc(), state.created_at.desc(), state.id)
        .correlate(Entry)
        .limit(1)
        .scalar_subquery()
    )

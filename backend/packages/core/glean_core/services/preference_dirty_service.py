"""Durable preference-rebuild outbox helpers."""

from collections.abc import Iterable

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from glean_database.models import User


async def mark_preferences_dirty(
    session: AsyncSession,
    user_ids: Iterable[str],
) -> int:
    """Increment preference revisions in the caller's transaction."""
    unique_user_ids = list(dict.fromkeys(str(user_id) for user_id in user_ids))
    if not unique_user_ids:
        return 0
    result = await session.execute(
        update(User)
        .where(User.id.in_(unique_user_ids))
        .values(preference_revision=User.preference_revision + 1)
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]

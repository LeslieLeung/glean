"""Durable preference outbox tests."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core.services.preference_dirty_service import mark_preferences_dirty
from glean_database.models import User


@pytest.mark.asyncio
async def test_dirty_revision_is_transactional_and_deduplicates_users(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    assert test_user.preference_revision == 0
    assert test_user.preference_synced_revision == 0

    updated = await mark_preferences_dirty(
        db_session,
        [test_user.id, test_user.id],
    )
    await db_session.commit()
    await db_session.refresh(test_user)

    assert updated == 1
    assert test_user.preference_revision == 1
    assert test_user.preference_synced_revision == 0

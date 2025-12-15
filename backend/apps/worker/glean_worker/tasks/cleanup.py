"""
Cleanup tasks.

Background tasks for cleaning up expired data.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, update
from sqlalchemy.engine import CursorResult

from glean_core import get_logger
from glean_database.models import UserEntry
from glean_database.session import get_session

logger = get_logger(__name__)


async def cleanup_read_later(ctx: dict[str, Any]) -> dict[str, int]:
    """
    Clean up expired read-later entries.

    Finds all user entries where:
    - read_later is True
    - read_later_until is set and has passed

    Sets read_later to False and clears read_later_until for these entries.

    Args:
        ctx: Task context dictionary.

    Returns:
        Dictionary with cleanup statistics.
    """
    logger.info("[cleanup_read_later] Starting read-later cleanup")

    cleaned_count = 0
    async for session in get_session():
        try:
            now = datetime.now(UTC)

            # Find and update expired entries
            stmt = (
                update(UserEntry)
                .where(
                    and_(
                        UserEntry.read_later.is_(True),
                        UserEntry.read_later_until.isnot(None),
                        UserEntry.read_later_until < now,
                    )
                )
                .values(read_later=False, read_later_until=None)
            )
            result: CursorResult[Any] = await session.execute(stmt)  # type: ignore[assignment]
            await session.commit()

            cleaned_count = result.rowcount or 0
            logger.info(
                f"[cleanup_read_later] Cleaned up {cleaned_count} expired read-later entries"
            )

        except Exception as e:
            logger.error(f"[cleanup_read_later] Error during cleanup: {e}")
            await session.rollback()
            raise

    return {"cleaned_count": cleaned_count}


async def scheduled_cleanup(ctx: dict[str, Any]) -> dict[str, int]:
    """
    Scheduled cleanup task.

    Called by cron job to run cleanup tasks.

    Args:
        ctx: Task context dictionary.

    Returns:
        Dictionary with cleanup statistics.
    """
    logger.info("[scheduled_cleanup] Running scheduled cleanup (hourly)")
    return await cleanup_read_later(ctx)

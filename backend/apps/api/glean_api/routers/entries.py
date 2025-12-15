"""
Entries router.

Provides endpoints for reading and managing feed entries.
"""

from typing import Annotated

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from glean_core.schemas import (
    EntryListResponse,
    EntryResponse,
    UpdateEntryStateRequest,
    UserResponse,
)
from glean_core.services import EntryService

from ..dependencies import get_current_user, get_entry_service, get_redis_pool, get_score_service

router = APIRouter()


@router.get("")
async def list_entries(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    entry_service: Annotated[EntryService, Depends(get_entry_service)],
    score_service: Annotated[object, Depends(get_score_service)],  # ScoreService | None
    feed_id: str | None = None,
    folder_id: str | None = None,
    is_read: bool | None = None,
    is_liked: bool | None = None,
    read_later: bool | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    view: str = Query("timeline", regex="^(timeline|smart)$"),
) -> EntryListResponse:
    """
    Get entries with filtering and pagination.

    Args:
        current_user: Current authenticated user.
        entry_service: Entry service.
        score_service: Score service for real-time preference scoring.
        feed_id: Optional filter by feed ID.
        folder_id: Optional filter by folder ID (gets entries from all feeds in folder).
        is_read: Optional filter by read status.
        is_liked: Optional filter by liked status.
        read_later: Optional filter by read later status.
        page: Page number (1-indexed).
        per_page: Items per page (max 100).
        view: View mode ("timeline" or "smart"). Smart view sorts by preference score.

    Returns:
        Paginated list of entries.
    """
    return await entry_service.get_entries(
        user_id=current_user.id,
        feed_id=feed_id,
        folder_id=folder_id,
        is_read=is_read,
        is_liked=is_liked,
        read_later=read_later,
        page=page,
        per_page=per_page,
        view=view,
        score_service=score_service,
    )


@router.get("/{entry_id}")
async def get_entry(
    entry_id: str,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    entry_service: Annotated[EntryService, Depends(get_entry_service)],
) -> EntryResponse:
    """
    Get a specific entry.

    Args:
        entry_id: Entry identifier.
        current_user: Current authenticated user.
        entry_service: Entry service.

    Returns:
        Entry details.

    Raises:
        HTTPException: If entry not found or user not subscribed to feed.
    """
    try:
        return await entry_service.get_entry(entry_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.patch("/{entry_id}")
async def update_entry_state(
    entry_id: str,
    data: UpdateEntryStateRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    entry_service: Annotated[EntryService, Depends(get_entry_service)],
) -> EntryResponse:
    """
    Update entry state (read, liked, read later).

    Args:
        entry_id: Entry identifier.
        data: State update data.
        current_user: Current authenticated user.
        entry_service: Entry service.

    Returns:
        Updated entry.

    Raises:
        HTTPException: If entry not found.
    """
    try:
        return await entry_service.update_entry_state(entry_id, current_user.id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


class MarkAllReadRequest(BaseModel):
    """Mark all read request body."""

    feed_id: str | None = None
    folder_id: str | None = None


@router.post("/mark-all-read")
async def mark_all_read(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    entry_service: Annotated[EntryService, Depends(get_entry_service)],
    data: MarkAllReadRequest,
) -> dict[str, str]:
    """
    Mark all entries as read.

    Args:
        current_user: Current authenticated user.
        entry_service: Entry service.
        data: Request body with optional feed_id and folder_id filters.

    Returns:
        Success message.
    """
    await entry_service.mark_all_read(current_user.id, data.feed_id, data.folder_id)
    return {"message": "All entries marked as read"}


# M3: Preference signal endpoints


@router.post("/{entry_id}/like")
async def like_entry(
    entry_id: str,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    entry_service: Annotated[EntryService, Depends(get_entry_service)],
    redis_pool: Annotated[ArqRedis, Depends(get_redis_pool)],
) -> EntryResponse:
    """
    Mark entry as liked.

    This is a convenience endpoint that sets is_liked=True and
    triggers preference model update.

    Args:
        entry_id: Entry identifier.
        current_user: Current authenticated user.
        entry_service: Entry service.
        redis_pool: Redis connection pool.

    Returns:
        Updated entry.

    Raises:
        HTTPException: If entry not found.
    """
    try:
        result = await entry_service.update_entry_state(
            entry_id, current_user.id, UpdateEntryStateRequest(is_liked=True)
        )

        # Queue preference update task (M3)
        try:
            await redis_pool.enqueue_job(
                "update_user_preference",
                user_id=current_user.id,
                entry_id=entry_id,
                signal_type="like",
            )
        except Exception:
            # Don't fail the request if preference update fails
            pass

        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.post("/{entry_id}/dislike")
async def dislike_entry(
    entry_id: str,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    entry_service: Annotated[EntryService, Depends(get_entry_service)],
    redis_pool: Annotated[ArqRedis, Depends(get_redis_pool)],
) -> EntryResponse:
    """
    Mark entry as disliked.

    This is a convenience endpoint that sets is_liked=False and
    triggers preference model update.

    Args:
        entry_id: Entry identifier.
        current_user: Current authenticated user.
        entry_service: Entry service.
        redis_pool: Redis connection pool.

    Returns:
        Updated entry.

    Raises:
        HTTPException: If entry not found.
    """
    try:
        result = await entry_service.update_entry_state(
            entry_id, current_user.id, UpdateEntryStateRequest(is_liked=False)
        )

        # Queue preference update task (M3)
        try:
            await redis_pool.enqueue_job(
                "update_user_preference",
                user_id=current_user.id,
                entry_id=entry_id,
                signal_type="dislike",
            )
        except Exception:
            # Don't fail the request if preference update fails
            pass

        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.delete("/{entry_id}/reaction")
async def remove_reaction(
    entry_id: str,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    entry_service: Annotated[EntryService, Depends(get_entry_service)],
) -> EntryResponse:
    """
    Remove like/dislike reaction from entry.

    This is a convenience endpoint that sets is_liked=None.

    Args:
        entry_id: Entry identifier.
        current_user: Current authenticated user.
        entry_service: Entry service.

    Returns:
        Updated entry.

    Raises:
        HTTPException: If entry not found.
    """
    try:
        return await entry_service.update_entry_state(
            entry_id, current_user.id, UpdateEntryStateRequest(is_liked=None)
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None

"""
Entries router.

Provides endpoints for reading and managing feed entries.
"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from glean_core.schemas import (
    EntryListResponse,
    EntryResponse,
    UpdateEntryStateRequest,
    UserResponse,
)
from glean_core.services import EntryService
from glean_core.services.entry_rank_snapshot import SmartCursorExpiredError
from glean_core.services.entry_ranker import EmbeddingReader

from ..dependencies import get_current_user, get_entry_service, get_ranking_vector_client

router = APIRouter()


@router.get("")
async def list_entries(
    request: Request,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    entry_service: Annotated[EntryService, Depends(get_entry_service)],
    feed_id: UUID | Literal[""] | None = None,
    folder_id: UUID | Literal[""] | None = None,
    is_read: bool | None = None,
    is_liked: bool | None = None,
    read_later: bool | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    view: Literal["timeline", "smart"] = "timeline",
    include_score: bool = False,
    global_smart: bool = False,
    use_cursor: bool = False,
    cursor: str | None = Query(None, max_length=64),
) -> EntryListResponse:
    """List entries in publication or recommendation order."""

    async def get_embeddings() -> EmbeddingReader | None:
        return await get_ranking_vector_client(request, entry_service.session)

    try:
        return await entry_service.get_entries(
            user_id=current_user.id,
            feed_id=str(feed_id) if feed_id is not None else None,
            folder_id=str(folder_id) if folder_id is not None else None,
            is_read=is_read,
            is_liked=is_liked,
            read_later=read_later,
            page=page,
            per_page=per_page,
            view=view,
            include_score=include_score,
            global_smart=global_smart,
            use_cursor=use_cursor,
            cursor=cursor,
            get_embeddings=get_embeddings,
        )
    except SmartCursorExpiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Smart list expired. Refresh the list to continue.",
        ) from exc


@router.get("/{entry_id}")
async def get_entry(
    entry_id: UUID,
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
        return await entry_service.get_entry(str(entry_id), current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.patch("/{entry_id}")
async def update_entry_state(
    entry_id: UUID,
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
        return await entry_service.update_entry_state(str(entry_id), current_user.id, data)
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
    entry_id: UUID,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    entry_service: Annotated[EntryService, Depends(get_entry_service)],
) -> EntryResponse:
    """
    Mark entry as liked.

    This is a convenience endpoint that sets is_liked=True and
    supplies feedback for recommendation scoring.

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
            str(entry_id), current_user.id, UpdateEntryStateRequest(is_liked=True)
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.post("/{entry_id}/dislike")
async def dislike_entry(
    entry_id: UUID,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    entry_service: Annotated[EntryService, Depends(get_entry_service)],
) -> EntryResponse:
    """
    Mark entry as disliked.

    This is a convenience endpoint that sets is_liked=False and
    supplies feedback for recommendation scoring.

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
            str(entry_id), current_user.id, UpdateEntryStateRequest(is_liked=False)
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.delete("/{entry_id}/reaction")
async def remove_reaction(
    entry_id: UUID,
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
            str(entry_id), current_user.id, UpdateEntryStateRequest(is_liked=None)
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None

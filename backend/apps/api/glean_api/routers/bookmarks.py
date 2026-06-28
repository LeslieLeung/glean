"""
Bookmarks router.

Provides endpoints for bookmark management.
"""

from typing import Annotated
from uuid import UUID

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Query, status

from glean_core.schemas import UserResponse
from glean_core.schemas.bookmark import (
    BookmarkCreate,
    BookmarkFolderRequest,
    BookmarkListResponse,
    BookmarkResponse,
    BookmarkTagRequest,
    BookmarkUpdate,
)
from glean_core.services import BookmarkService

from ..dependencies import get_bookmark_service, get_current_user, get_redis_pool

router = APIRouter()


@router.get("", response_model=BookmarkListResponse)
async def get_bookmarks(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    bookmark_service: Annotated[BookmarkService, Depends(get_bookmark_service)],
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    folder_id: str | None = Query(None, description="Filter by folder"),
    tag_ids: list[str] | None = Query(None, description="Filter by tags"),
    search: str | None = Query(None, description="Search in title"),
    sort: str = Query("created_at", description="Sort field"),
    order: str = Query("desc", description="Sort order"),
) -> BookmarkListResponse:
    """
    Get bookmarks with filtering and pagination.

    Args:
        current_user: Current authenticated user.
        bookmark_service: Bookmark service instance.
        page: Page number.
        per_page: Items per page.
        folder_id: Filter by folder ID.
        tag_ids: Filter by tag IDs (intersection).
        search: Search in title.
        sort: Sort field (created_at or title).
        order: Sort order (asc or desc).

    Returns:
        Paginated bookmark list.
    """
    return await bookmark_service.get_bookmarks(
        user_id=current_user.id,
        page=page,
        per_page=per_page,
        folder_id=folder_id,
        tag_ids=tag_ids,
        search=search,
        sort=sort,
        order=order,
    )


@router.post("", response_model=BookmarkResponse, status_code=status.HTTP_201_CREATED)
async def create_bookmark(
    data: BookmarkCreate,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    bookmark_service: Annotated[BookmarkService, Depends(get_bookmark_service)],
    redis: Annotated[ArqRedis, Depends(get_redis_pool)],
) -> BookmarkResponse:
    """
    Create a new bookmark.

    If the bookmark is created from a URL without title/excerpt,
    the metadata will be fetched asynchronously.

    Args:
        data: Bookmark creation data.
        current_user: Current authenticated user.
        bookmark_service: Bookmark service instance.
        redis: Redis connection for task queue.

    Returns:
        Created bookmark.

    Raises:
        HTTPException: If validation fails.
    """
    try:
        bookmark, needs_metadata_fetch = await bookmark_service.create_bookmark(
            current_user.id, data
        )

        # Queue metadata fetch task if needed
        if needs_metadata_fetch:
            await redis.enqueue_job(
                "fetch_bookmark_metadata_task",
                bookmark.id,
            )

        return bookmark
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/{bookmark_id}", response_model=BookmarkResponse)
async def get_bookmark(
    bookmark_id: UUID,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    bookmark_service: Annotated[BookmarkService, Depends(get_bookmark_service)],
) -> BookmarkResponse:
    """
    Get a specific bookmark.

    Args:
        bookmark_id: Bookmark identifier.
        current_user: Current authenticated user.
        bookmark_service: Bookmark service instance.

    Returns:
        Bookmark details.

    Raises:
        HTTPException: If bookmark not found.
    """
    try:
        return await bookmark_service.get_bookmark(str(bookmark_id), current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.patch("/{bookmark_id}", response_model=BookmarkResponse)
async def update_bookmark(
    bookmark_id: UUID,
    data: BookmarkUpdate,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    bookmark_service: Annotated[BookmarkService, Depends(get_bookmark_service)],
) -> BookmarkResponse:
    """
    Update a bookmark.

    Args:
        bookmark_id: Bookmark identifier.
        data: Update data.
        current_user: Current authenticated user.
        bookmark_service: Bookmark service instance.

    Returns:
        Updated bookmark.

    Raises:
        HTTPException: If bookmark not found.
    """
    try:
        return await bookmark_service.update_bookmark(str(bookmark_id), current_user.id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.delete("/{bookmark_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bookmark(
    bookmark_id: UUID,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    bookmark_service: Annotated[BookmarkService, Depends(get_bookmark_service)],
) -> None:
    """
    Delete a bookmark.

    Args:
        bookmark_id: Bookmark identifier.
        current_user: Current authenticated user.
        bookmark_service: Bookmark service instance.

    Raises:
        HTTPException: If bookmark not found.
    """
    try:
        await bookmark_service.delete_bookmark(str(bookmark_id), current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post("/{bookmark_id}/folders", response_model=BookmarkResponse)
async def add_folder_to_bookmark(
    bookmark_id: UUID,
    data: BookmarkFolderRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    bookmark_service: Annotated[BookmarkService, Depends(get_bookmark_service)],
) -> BookmarkResponse:
    """
    Add a folder to a bookmark.

    Args:
        bookmark_id: Bookmark identifier.
        data: Folder association data.
        current_user: Current authenticated user.
        bookmark_service: Bookmark service instance.

    Returns:
        Updated bookmark.

    Raises:
        HTTPException: If bookmark or folder not found.
    """
    try:
        return await bookmark_service.add_folder(str(bookmark_id), current_user.id, data.folder_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.delete("/{bookmark_id}/folders/{folder_id}", response_model=BookmarkResponse)
async def remove_folder_from_bookmark(
    bookmark_id: UUID,
    folder_id: UUID,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    bookmark_service: Annotated[BookmarkService, Depends(get_bookmark_service)],
) -> BookmarkResponse:
    """
    Remove a folder from a bookmark.

    Args:
        bookmark_id: Bookmark identifier.
        folder_id: Folder identifier.
        current_user: Current authenticated user.
        bookmark_service: Bookmark service instance.

    Returns:
        Updated bookmark.

    Raises:
        HTTPException: If bookmark not found.
    """
    try:
        return await bookmark_service.remove_folder(
            str(bookmark_id), current_user.id, str(folder_id)
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post("/{bookmark_id}/tags", response_model=BookmarkResponse)
async def add_tag_to_bookmark(
    bookmark_id: UUID,
    data: BookmarkTagRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    bookmark_service: Annotated[BookmarkService, Depends(get_bookmark_service)],
) -> BookmarkResponse:
    """
    Add a tag to a bookmark.

    Args:
        bookmark_id: Bookmark identifier.
        data: Tag association data.
        current_user: Current authenticated user.
        bookmark_service: Bookmark service instance.

    Returns:
        Updated bookmark.

    Raises:
        HTTPException: If bookmark or tag not found.
    """
    try:
        return await bookmark_service.add_tag(str(bookmark_id), current_user.id, data.tag_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.delete("/{bookmark_id}/tags/{tag_id}", response_model=BookmarkResponse)
async def remove_tag_from_bookmark(
    bookmark_id: UUID,
    tag_id: UUID,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    bookmark_service: Annotated[BookmarkService, Depends(get_bookmark_service)],
) -> BookmarkResponse:
    """
    Remove a tag from a bookmark.

    Args:
        bookmark_id: Bookmark identifier.
        tag_id: Tag identifier.
        current_user: Current authenticated user.
        bookmark_service: Bookmark service instance.

    Returns:
        Updated bookmark.

    Raises:
        HTTPException: If bookmark not found.
    """
    try:
        return await bookmark_service.remove_tag(str(bookmark_id), current_user.id, str(tag_id))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

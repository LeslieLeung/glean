"""
Tags router.

Provides endpoints for tag management.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from glean_core.schemas import UserResponse
from glean_core.schemas.tag import (
    TagBatchRequest,
    TagCreate,
    TagListResponse,
    TagResponse,
    TagUpdate,
)
from glean_core.services import TagService

from ..dependencies import get_current_user, get_tag_service

router = APIRouter()


@router.get("", response_model=TagListResponse)
async def get_tags(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    tag_service: Annotated[TagService, Depends(get_tag_service)],
) -> TagListResponse:
    """
    Get all tags for the current user.

    Args:
        current_user: Current authenticated user.
        tag_service: Tag service instance.

    Returns:
        List of tags with usage counts.
    """
    return await tag_service.get_tags(current_user.id)


@router.post("", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag(
    data: TagCreate,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    tag_service: Annotated[TagService, Depends(get_tag_service)],
) -> TagResponse:
    """
    Create a new tag.

    Args:
        data: Tag creation data.
        current_user: Current authenticated user.
        tag_service: Tag service instance.

    Returns:
        Created tag.

    Raises:
        HTTPException: If tag name already exists.
    """
    try:
        return await tag_service.create_tag(current_user.id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e


@router.get("/{tag_id}", response_model=TagResponse)
async def get_tag(
    tag_id: UUID,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    tag_service: Annotated[TagService, Depends(get_tag_service)],
) -> TagResponse:
    """
    Get a specific tag.

    Args:
        tag_id: Tag identifier.
        current_user: Current authenticated user.
        tag_service: Tag service instance.

    Returns:
        Tag details.

    Raises:
        HTTPException: If tag not found.
    """
    try:
        return await tag_service.get_tag(str(tag_id), current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.patch("/{tag_id}", response_model=TagResponse)
async def update_tag(
    tag_id: UUID,
    data: TagUpdate,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    tag_service: Annotated[TagService, Depends(get_tag_service)],
) -> TagResponse:
    """
    Update a tag.

    Args:
        tag_id: Tag identifier.
        data: Update data.
        current_user: Current authenticated user.
        tag_service: Tag service instance.

    Returns:
        Updated tag.

    Raises:
        HTTPException: If tag not found or name conflict.
    """
    try:
        return await tag_service.update_tag(str(tag_id), current_user.id, data)
    except ValueError as e:
        if "already exists" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: UUID,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    tag_service: Annotated[TagService, Depends(get_tag_service)],
) -> None:
    """
    Delete a tag.

    Args:
        tag_id: Tag identifier.
        current_user: Current authenticated user.
        tag_service: Tag service instance.

    Raises:
        HTTPException: If tag not found.
    """
    try:
        await tag_service.delete_tag(str(tag_id), current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post("/batch", status_code=status.HTTP_200_OK)
async def batch_tag_operation(
    data: TagBatchRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    tag_service: Annotated[TagService, Depends(get_tag_service)],
) -> dict[str, int]:
    """
    Batch add or remove tags from multiple targets.

    Args:
        data: Batch operation data.
        current_user: Current authenticated user.
        tag_service: Tag service instance.

    Returns:
        Number of items affected.

    Raises:
        HTTPException: If tag not found or invalid operation.
    """
    try:
        if data.action == "add":
            count = await tag_service.batch_add_tag(
                data.tag_id, current_user.id, data.target_type, data.target_ids
            )
        else:
            count = await tag_service.batch_remove_tag(
                data.tag_id, current_user.id, data.target_type, data.target_ids
            )
        return {"affected": count}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

"""
Folders router.

Provides endpoints for folder management.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from glean_core.schemas import UserResponse
from glean_core.schemas.folder import (
    FolderCreate,
    FolderMove,
    FolderReorder,
    FolderResponse,
    FolderTreeResponse,
    FolderUpdate,
)
from glean_core.services import FolderService

from ..dependencies import get_current_user, get_folder_service

router = APIRouter()


@router.get("", response_model=FolderTreeResponse)
async def get_folders(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    folder_service: Annotated[FolderService, Depends(get_folder_service)],
    type: str | None = Query(None, description="Folder type filter (feed/bookmark)"),
) -> FolderTreeResponse:
    """
    Get all folders as a tree structure.

    Args:
        current_user: Current authenticated user.
        folder_service: Folder service instance.
        type: Optional type filter.

    Returns:
        Folder tree response.
    """
    return await folder_service.get_folders_tree(current_user.id, type)


@router.post("", response_model=FolderResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(
    data: FolderCreate,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    folder_service: Annotated[FolderService, Depends(get_folder_service)],
) -> FolderResponse:
    """
    Create a new folder.

    Args:
        data: Folder creation data.
        current_user: Current authenticated user.
        folder_service: Folder service instance.

    Returns:
        Created folder.

    Raises:
        HTTPException: If validation fails.
    """
    try:
        return await folder_service.create_folder(current_user.id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/{folder_id}", response_model=FolderResponse)
async def get_folder(
    folder_id: UUID,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    folder_service: Annotated[FolderService, Depends(get_folder_service)],
) -> FolderResponse:
    """
    Get a specific folder.

    Args:
        folder_id: Folder identifier.
        current_user: Current authenticated user.
        folder_service: Folder service instance.

    Returns:
        Folder details.

    Raises:
        HTTPException: If folder not found.
    """
    try:
        return await folder_service.get_folder(str(folder_id), current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.patch("/{folder_id}", response_model=FolderResponse)
async def update_folder(
    folder_id: UUID,
    data: FolderUpdate,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    folder_service: Annotated[FolderService, Depends(get_folder_service)],
) -> FolderResponse:
    """
    Update a folder.

    Args:
        folder_id: Folder identifier.
        data: Update data.
        current_user: Current authenticated user.
        folder_service: Folder service instance.

    Returns:
        Updated folder.

    Raises:
        HTTPException: If folder not found.
    """
    try:
        return await folder_service.update_folder(str(folder_id), current_user.id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: UUID,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    folder_service: Annotated[FolderService, Depends(get_folder_service)],
) -> None:
    """
    Delete a folder.

    Args:
        folder_id: Folder identifier.
        current_user: Current authenticated user.
        folder_service: Folder service instance.

    Raises:
        HTTPException: If folder not found.
    """
    try:
        await folder_service.delete_folder(str(folder_id), current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post("/{folder_id}/move", response_model=FolderResponse)
async def move_folder(
    folder_id: UUID,
    data: FolderMove,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    folder_service: Annotated[FolderService, Depends(get_folder_service)],
) -> FolderResponse:
    """
    Move a folder to a new parent.

    Args:
        folder_id: Folder identifier.
        data: Move data with new parent_id.
        current_user: Current authenticated user.
        folder_service: Folder service instance.

    Returns:
        Updated folder.

    Raises:
        HTTPException: If validation fails.
    """
    try:
        return await folder_service.move_folder(str(folder_id), current_user.id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/reorder", status_code=status.HTTP_204_NO_CONTENT)
async def reorder_folders(
    data: FolderReorder,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    folder_service: Annotated[FolderService, Depends(get_folder_service)],
) -> None:
    """
    Batch update folder positions.

    Args:
        data: Reorder data with list of folder ID and position pairs.
        current_user: Current authenticated user.
        folder_service: Folder service instance.
    """
    await folder_service.reorder_folders(current_user.id, data.orders)

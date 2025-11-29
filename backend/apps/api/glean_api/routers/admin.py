"""
Admin router - Skeleton implementation.

This module provides administrative endpoints for system management.
"""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/stats")
async def get_stats() -> dict[str, int]:
    """
    Get system statistics.

    Returns:
        Dictionary containing various system metrics.
    """
    # TODO: Implement in M1
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/users")
async def list_users() -> list[dict[str, str]]:
    """
    List all registered users.

    Returns:
        List of user records.
    """
    # TODO: Implement in M1
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/feeds")
async def list_all_feeds() -> list[dict[str, str]]:
    """
    List all feeds in the system.

    Returns:
        List of all feed records.
    """
    # TODO: Implement in M1
    raise HTTPException(status_code=501, detail="Not implemented")

"""
Preference router.

Provides endpoints for user preference statistics and management.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from glean_core.schemas import UserResponse
from glean_core.services import PreferenceService

from ..dependencies import get_current_user, get_preference_service

router = APIRouter()


@router.get("/stats")
async def get_preference_stats(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    preference_service: Annotated[PreferenceService, Depends(get_preference_service)],
) -> dict[str, Any]:
    """
    Get user preference statistics.

    Returns aggregated statistics about user's likes, dislikes, bookmarks,
    and top sources/authors based on affinity.

    Args:
        current_user: Current authenticated user.
        preference_service: Preference service.

    Returns:
        Preference statistics.
    """
    stats = await preference_service.get_stats(current_user.id)
    return stats


@router.post("/rebuild")
async def rebuild_preference_model(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    preference_service: Annotated[PreferenceService, Depends(get_preference_service)],
) -> dict[str, str]:
    """
    Rebuild user preference model from scratch.

    This endpoint triggers a background job to rebuild the user's
    preference vectors and statistics from historical data.

    Args:
        current_user: Current authenticated user.
        preference_service: Preference service.

    Returns:
        Success message.
    """
    await preference_service.queue_rebuild(current_user.id)
    return {"message": "Preference model rebuild queued"}


@router.get("/strength")
async def get_preference_strength(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    preference_service: Annotated[PreferenceService, Depends(get_preference_service)],
) -> dict[str, str]:
    """
    Get preference model strength indicator.

    Returns "weak", "moderate", or "strong" based on the number
    of feedback signals collected.

    Args:
        current_user: Current authenticated user.
        preference_service: Preference service.

    Returns:
        Strength indicator.
    """
    strength = await preference_service.get_strength(current_user.id)
    return {"strength": strength}

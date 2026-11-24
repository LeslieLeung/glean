"""
Preference router.

Provides endpoints for user preference statistics and management.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from glean_core.schemas import UserResponse
from glean_core.services import PreferenceService

from ..dependencies import get_current_user, get_preference_service

router = APIRouter()


@router.get("/stats")
async def get_preference_stats(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    preference_service: Annotated[PreferenceService, Depends(get_preference_service)],
) -> dict[str, int]:
    """Get the user's current like, dislike and bookmark counts."""
    return await preference_service.get_stats(current_user.id)

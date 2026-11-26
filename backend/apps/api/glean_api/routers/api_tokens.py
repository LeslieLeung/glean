"""
API Tokens router.

Provides endpoints for API token management (create, list, revoke).
"""

from typing import Annotated
from uuid import UUID

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Request, status

from glean_core import RedisKeys
from glean_core.schemas import UserResponse
from glean_core.schemas.api_token import (
    APITokenCreate,
    APITokenCreateResponse,
    APITokenListResponse,
)
from glean_core.services import APITokenService

from ..dependencies import get_api_token_service, get_current_user, get_redis_pool
from .auth import enforce_rate_limit

router = APIRouter()
_CREATE_TOKEN_RATE_LIMIT = 10


@router.get("", response_model=APITokenListResponse)
async def list_tokens(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    token_service: Annotated[APITokenService, Depends(get_api_token_service)],
) -> APITokenListResponse:
    """
    List all API tokens for the current user.

    Args:
        current_user: Current authenticated user.
        token_service: API token service instance.

    Returns:
        List of tokens (without actual token values).
    """
    return await token_service.list_tokens(current_user.id)


@router.post("", response_model=APITokenCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_token(
    request: Request,
    data: APITokenCreate,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    token_service: Annotated[APITokenService, Depends(get_api_token_service)],
    redis: Annotated[ArqRedis, Depends(get_redis_pool)],
) -> APITokenCreateResponse:
    """
    Create a new API token.

    The plain token value is only returned once during creation.
    Make sure to save it securely.

    Args:
        data: Token creation data.
        current_user: Current authenticated user.
        token_service: API token service instance.

    Returns:
        Created token with the plain token value (only shown once).
    """
    await enforce_rate_limit(
        redis,
        request,
        RedisKeys.auth_rate_limit("create_token", current_user.id),
        limit=_CREATE_TOKEN_RATE_LIMIT,
        window_seconds=60,
    )
    try:
        return await token_service.create_token(
            user_id=current_user.id,
            name=data.name,
            expires_in_days=data.expires_in_days,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(
    token_id: UUID,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    token_service: Annotated[APITokenService, Depends(get_api_token_service)],
) -> None:
    """
    Revoke an API token.

    Args:
        token_id: Token identifier.
        current_user: Current authenticated user.
        token_service: API token service instance.

    Raises:
        HTTPException: If token not found.
    """
    try:
        await token_service.revoke_token(str(token_id), current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

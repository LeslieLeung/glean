"""
Admin router.

Provides endpoints for administrative operations.
"""

from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from jose import jwt

from glean_core.schemas.admin import (
    AdminLoginRequest,
    AdminLoginResponse,
    AdminUserResponse,
    DashboardStatsResponse,
    ToggleUserStatusRequest,
    UserListItem,
    UserListResponse,
)
from glean_core.services import AdminService

from ..config import settings
from ..dependencies import get_admin_service, get_current_admin

router = APIRouter()


@router.post("/auth/login", response_model=AdminLoginResponse)
async def admin_login(
    request: AdminLoginRequest,
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
) -> AdminLoginResponse:
    """
    Admin login endpoint.

    Args:
        request: Login credentials.
        admin_service: Admin service instance.

    Returns:
        Access token and admin info.

    Raises:
        HTTPException: If credentials are invalid.
    """
    admin = await admin_service.authenticate_admin(request.username, request.password)

    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Create JWT token with admin claims
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)

    # AdminRole is a str Enum, so .value gives us the string representation
    role_value = admin.role.value

    payload = {
        "sub": admin.id,
        "username": admin.username,
        "role": role_value,
        "type": "admin",
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
    }

    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)

    # Build response with explicit field values to avoid lazy loading issues
    admin_response = AdminUserResponse(
        id=admin.id,
        username=admin.username,
        role=role_value,
        is_active=admin.is_active,
        last_login_at=admin.last_login_at,
        created_at=admin.created_at,
        updated_at=admin.updated_at,
    )

    return AdminLoginResponse(access_token=token, token_type="bearer", admin=admin_response)


@router.get("/me", response_model=AdminUserResponse)
async def get_current_admin_info(
    current_admin: Annotated[AdminUserResponse, Depends(get_current_admin)],
) -> AdminUserResponse:
    """
    Get current admin information.

    Args:
        current_admin: Current authenticated admin.

    Returns:
        Admin user information.
    """
    return current_admin


@router.get("/health")
async def admin_health() -> dict[str, str]:
    """
    Admin health check endpoint.

    Returns:
        Health status.
    """
    return {"status": "healthy", "message": "Admin API is running"}


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    current_admin: Annotated[AdminUserResponse, Depends(get_current_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
) -> DashboardStatsResponse:
    """
    Get dashboard statistics.

    Args:
        current_admin: Current authenticated admin.
        admin_service: Admin service instance.

    Returns:
        Dashboard statistics.
    """
    stats = await admin_service.get_dashboard_stats()
    return DashboardStatsResponse(**stats)


@router.get("/users", response_model=UserListResponse)
async def list_users(
    current_admin: Annotated[AdminUserResponse, Depends(get_current_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    search: str | None = Query(None, description="Search by email"),
) -> UserListResponse:
    """
    List all users with pagination.

    Args:
        current_admin: Current authenticated admin.
        admin_service: Admin service instance.
        page: Page number.
        per_page: Items per page.
        search: Search query.

    Returns:
        Paginated user list.
    """
    users, total = await admin_service.list_users(page=page, per_page=per_page, search=search)

    return UserListResponse(
        items=[UserListItem.model_validate(user) for user in users],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=ceil(total / per_page) if total > 0 else 1,
    )


@router.patch("/users/{user_id}/status", response_model=UserListItem)
async def toggle_user_status(
    user_id: str,
    request: ToggleUserStatusRequest,
    current_admin: Annotated[AdminUserResponse, Depends(get_current_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
) -> UserListItem:
    """
    Enable or disable a user account.

    Args:
        user_id: User ID to update.
        request: New status.
        current_admin: Current authenticated admin.
        admin_service: Admin service instance.

    Returns:
        Updated user information.

    Raises:
        HTTPException: If user not found.
    """
    user = await admin_service.toggle_user_status(user_id, request.is_active)

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return UserListItem.model_validate(user)

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
    AdminBatchEntryRequest,
    AdminBatchFeedRequest,
    AdminEntryDetailResponse,
    AdminEntryListItem,
    AdminEntryListResponse,
    AdminFeedDetailResponse,
    AdminFeedListItem,
    AdminFeedListResponse,
    AdminFeedUpdateRequest,
    AdminLoginRequest,
    AdminLoginResponse,
    AdminUserResponse,
    DashboardStatsResponse,
    ToggleUserStatusRequest,
    UserListItem,
    UserListResponse,
)
from glean_core.services import AdminService, SystemService

from ..config import settings
from ..dependencies import get_admin_service, get_current_admin, get_system_service

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

    # Handle both enum (in-memory) and string (from database) cases
    role_value = admin.role.value if hasattr(admin.role, "value") else admin.role

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


# M2: Feed management endpoints
@router.get("/feeds", response_model=AdminFeedListResponse)
async def list_feeds(
    current_admin: Annotated[AdminUserResponse, Depends(get_current_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    status_filter: str | None = Query(None, alias="status", description="Filter by status"),
    search: str | None = Query(None, description="Search in title or URL"),
    sort: str = Query("created_at", description="Sort field"),
    order: str = Query("desc", description="Sort order"),
) -> AdminFeedListResponse:
    """
    List all feeds with pagination.

    Args:
        current_admin: Current authenticated admin.
        admin_service: Admin service instance.
        page: Page number.
        per_page: Items per page.
        status_filter: Filter by status.
        search: Search query.
        sort: Sort field.
        order: Sort order.

    Returns:
        Paginated feed list.
    """
    feeds, total = await admin_service.list_feeds(
        page=page,
        per_page=per_page,
        status=status_filter,
        search=search,
        sort=sort,
        order=order,
    )

    return AdminFeedListResponse(
        items=[AdminFeedListItem(**feed) for feed in feeds],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=ceil(total / per_page) if total > 0 else 1,
    )


@router.get("/feeds/{feed_id}", response_model=AdminFeedDetailResponse)
async def get_feed(
    feed_id: str,
    current_admin: Annotated[AdminUserResponse, Depends(get_current_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
) -> AdminFeedDetailResponse:
    """
    Get feed details.

    Args:
        feed_id: Feed ID.
        current_admin: Current authenticated admin.
        admin_service: Admin service instance.

    Returns:
        Feed details.

    Raises:
        HTTPException: If feed not found.
    """
    feed = await admin_service.get_feed(feed_id)

    if not feed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feed not found")

    return AdminFeedDetailResponse(**feed)


@router.patch("/feeds/{feed_id}", response_model=AdminFeedDetailResponse)
async def update_feed(
    feed_id: str,
    request: AdminFeedUpdateRequest,
    current_admin: Annotated[AdminUserResponse, Depends(get_current_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
) -> AdminFeedDetailResponse:
    """
    Update a feed.

    Args:
        feed_id: Feed ID.
        request: Update data.
        current_admin: Current authenticated admin.
        admin_service: Admin service instance.

    Returns:
        Updated feed.

    Raises:
        HTTPException: If feed not found.
    """
    feed = await admin_service.update_feed(
        feed_id, url=request.url, title=request.title, status=request.status
    )

    if not feed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feed not found")

    return AdminFeedDetailResponse(**feed)


@router.post("/feeds/{feed_id}/reset-error", response_model=AdminFeedDetailResponse)
async def reset_feed_error(
    feed_id: str,
    current_admin: Annotated[AdminUserResponse, Depends(get_current_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
) -> AdminFeedDetailResponse:
    """
    Reset error count for a feed.

    Args:
        feed_id: Feed ID.
        current_admin: Current authenticated admin.
        admin_service: Admin service instance.

    Returns:
        Updated feed.

    Raises:
        HTTPException: If feed not found.
    """
    feed = await admin_service.reset_feed_error(feed_id)

    if not feed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feed not found")

    return AdminFeedDetailResponse(**feed)


@router.delete("/feeds/{feed_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feed(
    feed_id: str,
    current_admin: Annotated[AdminUserResponse, Depends(get_current_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
) -> None:
    """
    Delete a feed.

    Args:
        feed_id: Feed ID.
        current_admin: Current authenticated admin.
        admin_service: Admin service instance.

    Raises:
        HTTPException: If feed not found.
    """
    deleted = await admin_service.delete_feed(feed_id)

    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feed not found")


@router.post("/feeds/batch")
async def batch_feed_operation(
    request: AdminBatchFeedRequest,
    current_admin: Annotated[AdminUserResponse, Depends(get_current_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
) -> dict[str, int]:
    """
    Perform batch operation on feeds.

    Args:
        request: Batch operation data.
        current_admin: Current authenticated admin.
        admin_service: Admin service instance.

    Returns:
        Number of affected feeds.
    """
    count = await admin_service.batch_feed_operation(request.action, request.feed_ids)
    return {"affected": count}


# M2: Entry management endpoints
@router.get("/entries", response_model=AdminEntryListResponse)
async def list_entries(
    current_admin: Annotated[AdminUserResponse, Depends(get_current_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    feed_id: str | None = Query(None, description="Filter by feed"),
    search: str | None = Query(None, description="Search in title"),
    sort: str = Query("created_at", description="Sort field"),
    order: str = Query("desc", description="Sort order"),
) -> AdminEntryListResponse:
    """
    List all entries with pagination.

    Args:
        current_admin: Current authenticated admin.
        admin_service: Admin service instance.
        page: Page number.
        per_page: Items per page.
        feed_id: Filter by feed.
        search: Search query.
        sort: Sort field.
        order: Sort order.

    Returns:
        Paginated entry list.
    """
    entries, total = await admin_service.list_entries(
        page=page,
        per_page=per_page,
        feed_id=feed_id,
        search=search,
        sort=sort,
        order=order,
    )

    return AdminEntryListResponse(
        items=[AdminEntryListItem(**entry) for entry in entries],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=ceil(total / per_page) if total > 0 else 1,
    )


@router.get("/entries/{entry_id}", response_model=AdminEntryDetailResponse)
async def get_entry(
    entry_id: str,
    current_admin: Annotated[AdminUserResponse, Depends(get_current_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
) -> AdminEntryDetailResponse:
    """
    Get entry details.

    Args:
        entry_id: Entry ID.
        current_admin: Current authenticated admin.
        admin_service: Admin service instance.

    Returns:
        Entry details.

    Raises:
        HTTPException: If entry not found.
    """
    entry = await admin_service.get_entry(entry_id)

    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")

    return AdminEntryDetailResponse(**entry)


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(
    entry_id: str,
    current_admin: Annotated[AdminUserResponse, Depends(get_current_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
) -> None:
    """
    Delete an entry.

    Args:
        entry_id: Entry ID.
        current_admin: Current authenticated admin.
        admin_service: Admin service instance.

    Raises:
        HTTPException: If entry not found.
    """
    deleted = await admin_service.delete_entry(entry_id)

    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")


@router.post("/entries/batch")
async def batch_entry_operation(
    request: AdminBatchEntryRequest,
    current_admin: Annotated[AdminUserResponse, Depends(get_current_admin)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
) -> dict[str, int]:
    """
    Perform batch operation on entries.

    Args:
        request: Batch operation data.
        current_admin: Current authenticated admin.
        admin_service: Admin service instance.

    Returns:
        Number of affected entries.
    """
    count = await admin_service.batch_entry_operation(request.action, request.entry_ids)
    return {"affected": count}


# System Settings
@router.get("/settings/registration", response_model=dict[str, bool])
async def get_registration_status(
    current_admin: Annotated[AdminUserResponse, Depends(get_current_admin)],
    system_service: Annotated[SystemService, Depends(get_system_service)],
) -> dict[str, bool]:
    """
    Get registration enabled status.

    Args:
        current_admin: Current authenticated admin.
        system_service: System service instance.

    Returns:
        Registration status.
    """
    enabled = await system_service.is_registration_enabled()
    return {"enabled": enabled}


@router.post("/settings/registration", response_model=dict[str, bool])
async def set_registration_status(
    enabled: bool,
    current_admin: Annotated[AdminUserResponse, Depends(get_current_admin)],
    system_service: Annotated[SystemService, Depends(get_system_service)],
) -> dict[str, bool]:
    """
    Set registration enabled status.

    Args:
        enabled: New status.
        current_admin: Current authenticated admin.
        system_service: System service instance.

    Returns:
        New registration status.
    """
    await system_service.set_registration_enabled(enabled)
    return {"enabled": enabled}

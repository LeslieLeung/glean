"""
Admin router.

Provides endpoints for administrative operations.
"""

from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Annotated

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core.schemas import EmbeddingConfigUpdateRequest
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
from glean_core.services import AdminService
from glean_database.session import get_session

from ..config import settings
from ..dependencies import (
    get_admin_service,
    get_current_admin,
    get_redis_pool,
)

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

    # Create JWT tokens with admin claims
    now = datetime.now(UTC)
    access_expire = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    refresh_expire = now + timedelta(days=settings.jwt_refresh_token_expire_days)

    # Handle both enum (in-memory) and string (from database) cases
    role_value = admin.role.value if hasattr(admin.role, "value") else admin.role

    # Access token payload
    access_payload = {
        "sub": admin.id,
        "username": admin.username,
        "role": role_value,
        "type": "admin",
        "exp": int(access_expire.timestamp()),
        "iat": int(now.timestamp()),
    }

    # Refresh token payload
    refresh_payload = {
        "sub": admin.id,
        "type": "admin_refresh",
        "exp": int(refresh_expire.timestamp()),
        "iat": int(now.timestamp()),
    }

    access_token = jwt.encode(
        access_payload, settings.secret_key, algorithm=settings.jwt_algorithm
    )
    refresh_token = jwt.encode(
        refresh_payload, settings.secret_key, algorithm=settings.jwt_algorithm
    )

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

    return AdminLoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        admin=admin_response,
    )


@router.post("/auth/refresh")
async def admin_refresh_token(
    request: dict[str, str],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
) -> dict[str, str]:
    """
    Refresh admin access token using refresh token.

    Args:
        request: Request body with refresh_token.
        admin_service: Admin service instance.

    Returns:
        New access and refresh tokens.

    Raises:
        HTTPException: If refresh token is invalid.
    """
    try:
        refresh_token = request.get("refresh_token")
        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="refresh_token is required",
            )

        # Verify refresh token
        payload = jwt.decode(
            refresh_token, settings.secret_key, algorithms=[settings.jwt_algorithm]
        )

        # Check token type
        if payload.get("type") != "admin_refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token type",
            )

        # Get admin ID from token
        admin_id = payload.get("sub")
        if not admin_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

        # Verify admin still exists and is active
        admin = await admin_service.get_admin_by_id(admin_id)
        if not admin or not admin.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Admin not found or inactive",
            )

        # Generate new tokens
        now = datetime.now(UTC)
        access_expire = now + timedelta(
            minutes=settings.jwt_access_token_expire_minutes
        )
        refresh_expire = now + timedelta(days=settings.jwt_refresh_token_expire_days)

        # Handle both enum (in-memory) and string (from database) cases
        role_value = admin.role.value if hasattr(admin.role, "value") else admin.role

        # Access token payload
        access_payload = {
            "sub": admin.id,
            "username": admin.username,
            "role": role_value,
            "type": "admin",
            "exp": int(access_expire.timestamp()),
            "iat": int(now.timestamp()),
        }

        # Refresh token payload
        refresh_payload = {
            "sub": admin.id,
            "type": "admin_refresh",
            "exp": int(refresh_expire.timestamp()),
            "iat": int(now.timestamp()),
        }

        new_access_token = jwt.encode(
            access_payload, settings.secret_key, algorithm=settings.jwt_algorithm
        )
        new_refresh_token = jwt.encode(
            refresh_payload, settings.secret_key, algorithm=settings.jwt_algorithm
        )

        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid refresh token: {str(e)}",
        ) from e


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


# =========================
# Embedding configuration
# =========================
@router.get("/embedding/config")
async def get_embedding_config(
    current_admin: Annotated[AdminUserResponse, Depends(get_current_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get current embedding configuration.

    Returns typed config with defaults for unset fields.
    """
    from glean_core.schemas.config import EmbeddingConfig
    from glean_core.schemas.config import (
        EmbeddingConfigResponse as TypedEmbeddingConfigResponse,
    )
    from glean_core.services import TypedConfigService

    config_service = TypedConfigService(session)
    config = await config_service.get(EmbeddingConfig)
    return TypedEmbeddingConfigResponse.from_config(config)


@router.post("/embedding/test")
async def test_embedding_provider(
    request: EmbeddingConfigUpdateRequest,
    current_admin: Annotated[AdminUserResponse, Depends(get_current_admin)],
):
    """
    Test embedding provider and infer dimension without saving configuration.

    This endpoint allows the frontend to test the provider configuration
    and display the inferred dimension to the user before saving.
    """
    from glean_vector.services.validation_service import EmbeddingValidationService

    validation_service = EmbeddingValidationService()

    # Infer dimension from provider
    result = await validation_service.infer_dimension(
        provider=request.provider or "",
        model=request.model or "",
        api_key=request.api_key,
        base_url=request.base_url,
    )

    if not result.success:
        raise HTTPException(
            status_code=400,
            detail=result.message,
        )

    return result


@router.put("/embedding/config")
async def update_embedding_config(
    request: EmbeddingConfigUpdateRequest,
    current_admin: Annotated[AdminUserResponse, Depends(get_current_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_pool: Annotated[ArqRedis, Depends(get_redis_pool)],
):
    """
    Update embedding provider configuration.

    If dimension is not provided, it will be auto-inferred from the provider.
    If enabled and config changed, triggers validation and rebuild.
    """
    from glean_core.schemas.config import (
        EmbeddingConfig,
        VectorizationStatus,
    )
    from glean_core.schemas.config import (
        EmbeddingConfigResponse as TypedEmbeddingConfigResponse,
    )
    from glean_core.services import TypedConfigService
    from glean_vector.services.validation_service import EmbeddingValidationService

    config_service = TypedConfigService(session)
    current = await config_service.get(EmbeddingConfig)

    # Build updates dict from request
    updates = request.model_dump(exclude_unset=True)

    # Auto-infer dimension if not provided and provider/model changed
    provider_changed = "provider" in updates or "model" in updates
    if provider_changed and "dimension" not in updates:
        # Use new values or fall back to current
        provider = updates.get("provider", current.provider)
        model = updates.get("model", current.model)
        api_key = updates.get("api_key", current.api_key)
        base_url = updates.get("base_url", current.base_url)

        # Infer dimension
        validation_service = EmbeddingValidationService()
        infer_result = await validation_service.infer_dimension(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
        )

        if not infer_result.success:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to infer dimension: {infer_result.message}",
            )

        # Add inferred dimension to updates
        inferred_dimension = infer_result.details.get("dimension")
        updates["dimension"] = inferred_dimension

    # Check if this is a config change that requires rebuild
    config_changed = False
    rebuild_fields = {"provider", "model", "dimension", "api_key", "base_url"}
    for field in rebuild_fields:
        if field in updates and getattr(current, field) != updates[field]:
            config_changed = True
            break

    # Apply updates
    updated = await config_service.update(EmbeddingConfig, **updates)

    # If enabled and config changed, trigger rebuild
    if updated.enabled and config_changed:
        # Generate new version and trigger rebuild
        await config_service.update_embedding_version()
        await config_service.update(
            EmbeddingConfig, status=VectorizationStatus.VALIDATING
        )
        await redis_pool.enqueue_job("validate_and_rebuild_embeddings")

    return TypedEmbeddingConfigResponse.from_config(updated)


@router.post("/embedding/enable")
async def enable_embedding(
    current_admin: Annotated[AdminUserResponse, Depends(get_current_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_pool: Annotated[ArqRedis, Depends(get_redis_pool)],
):
    """
    Enable vectorization.

    Validates provider and Milvus connection, then triggers rebuild.
    """
    from glean_core.schemas.config import (
        EmbeddingConfig,
        VectorizationStatus,
    )
    from glean_core.schemas.config import (
        EmbeddingConfigResponse as TypedEmbeddingConfigResponse,
    )
    from glean_core.services import TypedConfigService

    config_service = TypedConfigService(session)
    config = await config_service.get(EmbeddingConfig)

    if config.enabled:
        return TypedEmbeddingConfigResponse.from_config(config)

    # Enable and set to validating
    updated = await config_service.update(
        EmbeddingConfig,
        enabled=True,
        status=VectorizationStatus.VALIDATING,
    )

    # Trigger validation and rebuild in background
    await redis_pool.enqueue_job("validate_and_rebuild_embeddings")

    return TypedEmbeddingConfigResponse.from_config(updated)


@router.post("/embedding/disable")
async def disable_embedding(
    current_admin: Annotated[AdminUserResponse, Depends(get_current_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Disable vectorization.

    Stops processing and sets status to DISABLED.
    """
    from glean_core.schemas.config import (
        EmbeddingConfig,
        VectorizationStatus,
    )
    from glean_core.schemas.config import (
        EmbeddingConfigResponse as TypedEmbeddingConfigResponse,
    )
    from glean_core.services import TypedConfigService

    config_service = TypedConfigService(session)
    updated = await config_service.update(
        EmbeddingConfig,
        enabled=False,
        status=VectorizationStatus.DISABLED,
        rebuild_id=None,
        rebuild_started_at=None,
    )

    return TypedEmbeddingConfigResponse.from_config(updated)


@router.post("/embedding/validate")
async def validate_embedding_config(
    current_admin: Annotated[AdminUserResponse, Depends(get_current_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """
    Test provider and Milvus connection without saving.

    Returns validation results.
    """
    from glean_core.schemas.config import EmbeddingConfig
    from glean_core.services import TypedConfigService
    from glean_vector.services import EmbeddingValidationService

    config_service = TypedConfigService(session)
    config = await config_service.get(EmbeddingConfig)

    validation_service = EmbeddingValidationService()
    result = await validation_service.validate_full(config)

    return {
        "success": result.success,
        "message": result.message,
        "details": result.details,
    }


@router.post("/embedding/rebuild")
async def trigger_embedding_rebuild(
    current_admin: Annotated[AdminUserResponse, Depends(get_current_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_pool: Annotated[ArqRedis, Depends(get_redis_pool)],
) -> dict:
    """
    Manually trigger embedding rebuild.

    Only works if vectorization is enabled.
    """
    from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus
    from glean_core.services import TypedConfigService

    config_service = TypedConfigService(session)
    config = await config_service.get(EmbeddingConfig)

    if not config.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vectorization is not enabled",
        )

    if config.status == VectorizationStatus.REBUILDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rebuild already in progress",
        )

    # Generate new version and trigger rebuild
    await config_service.update_embedding_version()
    await config_service.update(EmbeddingConfig, status=VectorizationStatus.VALIDATING)
    await redis_pool.enqueue_job("validate_and_rebuild_embeddings")

    return {"message": "Rebuild triggered", "status": "validating"}


@router.post("/embedding/cancel-rebuild")
async def cancel_embedding_rebuild(
    current_admin: Annotated[AdminUserResponse, Depends(get_current_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """
    Cancel ongoing embedding rebuild.
    """
    from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus
    from glean_core.services import TypedConfigService

    config_service = TypedConfigService(session)
    config = await config_service.get(EmbeddingConfig)

    if config.status != VectorizationStatus.REBUILDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No rebuild in progress",
        )

    # Set status back to IDLE (or ERROR if there was an error)
    await config_service.update(
        EmbeddingConfig,
        status=VectorizationStatus.IDLE,
        rebuild_id=None,
        rebuild_started_at=None,
    )

    return {"message": "Rebuild cancelled", "status": "idle"}


@router.get("/embedding/status")
async def get_embedding_status(
    current_admin: Annotated[AdminUserResponse, Depends(get_current_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    admin_service: Annotated[AdminService, Depends(get_admin_service)],
) -> dict:
    """
    Get embedding system status and rebuild progress.

    If status is REBUILDING and all entries are processed (done + failed == total),
    automatically updates status to IDLE.
    """
    from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus
    from glean_core.services import TypedConfigService

    config_service = TypedConfigService(session)
    config = await config_service.get(EmbeddingConfig)

    # Get progress from entry counts
    progress = await admin_service.get_embedding_progress()

    # Auto-complete rebuild if all entries are processed
    current_status = config.status
    if config.status == VectorizationStatus.REBUILDING:
        total = progress.get("total", 0)
        done = progress.get("done", 0)
        failed = progress.get("failed", 0)

        # If all entries are processed (done + failed == total), mark as complete
        if total > 0 and (done + failed) >= total:
            await config_service.complete_rebuild()
            current_status = VectorizationStatus.IDLE

    return {
        "enabled": config.enabled,
        "status": current_status.value,
        "has_error": current_status == VectorizationStatus.ERROR,
        "error_message": config.last_error,
        "error_count": config.error_count,
        "rebuild_id": config.rebuild_id,
        "rebuild_started_at": (
            config.rebuild_started_at.isoformat() if config.rebuild_started_at else None
        ),
        "progress": progress,
    }

"""
FastAPI dependencies.

Provides dependency injection for database sessions, authentication, and services.
"""

from typing import Annotated

from arq.connections import ArqRedis
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core.auth import JWTConfig, verify_token
from glean_core.schemas import UserResponse
from glean_core.schemas.admin import AdminUserResponse
from glean_core.services import (
    AdminService,
    AuthService,
    BookmarkService,
    EntryService,
    FeedService,
    FolderService,
    PreferenceService,
    SystemConfigService,
    TagService,
    UserService,
)
from glean_database.session import get_session

from .config import settings

# Security scheme for JWT bearer tokens
security = HTTPBearer()


async def get_redis_pool() -> ArqRedis:
    """
    Get Redis connection pool for task queue.

    Returns:
        ArqRedis connection pool.
    """
    from .main import get_redis_pool as _get_redis_pool

    return await _get_redis_pool()


def get_jwt_config() -> JWTConfig:
    """
    Get JWT configuration.

    Returns:
        JWT configuration instance.
    """
    return JWTConfig(
        secret_key=settings.secret_key,
        algorithm=settings.jwt_algorithm,
        access_token_expire_minutes=settings.jwt_access_token_expire_minutes,
        refresh_token_expire_days=settings.jwt_refresh_token_expire_days,
    )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    session: Annotated[AsyncSession, Depends(get_session)],
    jwt_config: Annotated[JWTConfig, Depends(get_jwt_config)],
) -> UserResponse:
    """
    Get current authenticated user from JWT token.

    Args:
        credentials: HTTP bearer credentials.
        session: Database session.
        jwt_config: JWT configuration.

    Returns:
        Current user information.

    Raises:
        HTTPException: If token is invalid or user not found.
    """
    token = credentials.credentials
    token_data = verify_token(token, jwt_config)

    if not token_data or token_data.type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_service = AuthService(session, jwt_config)
    try:
        user = await auth_service.get_current_user(token)
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


# Service dependencies
def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    jwt_config: Annotated[JWTConfig, Depends(get_jwt_config)],
) -> AuthService:
    """Get authentication service instance."""
    return AuthService(session, jwt_config)


def get_user_service(session: Annotated[AsyncSession, Depends(get_session)]) -> UserService:
    """Get user service instance."""
    return UserService(session)


def get_feed_service(session: Annotated[AsyncSession, Depends(get_session)]) -> FeedService:
    """Get feed service instance."""
    return FeedService(session)


async def get_entry_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_pool: Annotated[ArqRedis, Depends(get_redis_pool)],
) -> EntryService:
    """Get entry service instance."""
    return EntryService(session, redis_pool)


def get_admin_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AdminService:
    """Get admin service instance."""
    return AdminService(session)


def get_system_config_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SystemConfigService:
    """Get system config service instance."""
    return SystemConfigService(session)


# M2 service dependencies
def get_folder_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FolderService:
    """Get folder service instance."""
    return FolderService(session)


def get_tag_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TagService:
    """Get tag service instance."""
    return TagService(session)


async def get_bookmark_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_pool: Annotated[ArqRedis, Depends(get_redis_pool)],
) -> BookmarkService:
    """Get bookmark service instance."""
    return BookmarkService(session, redis_pool)


# M3 service dependencies
async def get_preference_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_pool: Annotated[ArqRedis, Depends(get_redis_pool)],
) -> PreferenceService:
    """Get preference service instance."""
    return PreferenceService(session, redis_pool)


async def get_score_service(
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get score service instance for real-time preference scoring.

    Returns:
    - ScoreService if vectorization is enabled and Milvus is available
    - SimpleScoreService if vectorization is disabled
    - None if there's an error
    """
    from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus
    from glean_core.services import SimpleScoreService, TypedConfigService

    # Check if vectorization is enabled
    config_service = TypedConfigService(session)
    config = await config_service.get(EmbeddingConfig)

    if not config.enabled or config.status not in (
        VectorizationStatus.IDLE,
        VectorizationStatus.REBUILDING,
    ):
        # Vectorization disabled - use simple scoring
        return SimpleScoreService(session)

    # Vectorization enabled - try to use vector scoring
    try:
        from glean_vector.clients.milvus_client import MilvusClient
        from glean_vector.services.score_service import ScoreService

        milvus_client = MilvusClient()
        milvus_client.connect()
        milvus_client.ensure_collections(
            config.dimension, config.provider, config.model
        )

        return ScoreService(db_session=session, milvus_client=milvus_client)
    except Exception:
        # Milvus not available, fall back to simple scoring
        return SimpleScoreService(session)


async def get_current_admin(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    session: Annotated[AsyncSession, Depends(get_session)],
    jwt_config: Annotated[JWTConfig, Depends(get_jwt_config)],
) -> AdminUserResponse:
    """
    Get current authenticated admin from JWT token.

    Args:
        credentials: HTTP bearer credentials.
        session: Database session.
        jwt_config: JWT configuration.

    Returns:
        Current admin information.

    Raises:
        HTTPException: If token is invalid, not admin token, or admin not found.
    """
    from jose import JWTError, jwt

    token = credentials.credentials

    # Decode admin token directly instead of using verify_token
    # (which expects "access" or "refresh" type, not "admin")
    try:
        payload = jwt.decode(token, jwt_config.secret_key, algorithms=[jwt_config.algorithm])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    # Check if token is admin type
    if payload.get("type") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    # Get admin ID from token
    admin_id = payload.get("sub")
    if not admin_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get admin from database
    admin_service = AdminService(session)
    admin = await admin_service.get_admin_by_id(admin_id)

    if not admin or not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Build response with explicit field values to avoid lazy loading issues
    # Handle both enum (in-memory) and string (from database) cases
    role_value = admin.role.value if hasattr(admin.role, "value") else admin.role

    return AdminUserResponse(
        id=admin.id,
        username=admin.username,
        role=role_value,
        is_active=admin.is_active,
        last_login_at=admin.last_login_at,
        created_at=admin.created_at,
        updated_at=admin.updated_at,
    )

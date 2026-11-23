"""
Authentication router.

Provides endpoints for user registration, login, token refresh, and user profile.
"""

import ipaddress
from typing import Annotated, cast

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from glean_core import RedisKeys, get_logger
from glean_core.schemas import (
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
    UserUpdate,
)
from glean_core.services import AuthService, TypedConfigService, UserService

from ..dependencies import (
    get_auth_service,
    get_current_user,
    get_redis_pool,
    get_typed_config_service,
    get_user_service,
)

router = APIRouter()
logger = get_logger(__name__)


def _parse_ip(ip_value: str) -> str | None:
    """Return normalized IP string when valid, otherwise None."""
    try:
        return str(ipaddress.ip_address(ip_value.strip()))
    except ValueError:
        return None


def _parse_csv_config(value: str) -> list[str]:
    """Parse comma-separated config into normalized values."""
    return [item.strip() for item in value.split(",") if item.strip()]


def _authentication_failed_exception() -> HTTPException:
    """Create a generic auth failure response without internal details."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication failed. Please try again.",
    )


def _oidc_no_cache_headers() -> dict[str, str]:
    """Standard no-cache and security headers for OIDC responses."""
    return {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
    }


def _get_client_identifier(request: Request) -> str:
    """Get client IP for rate limiting with trusted proxy header handling."""
    from glean_core.config import auth_provider_config

    direct_ip = _parse_ip(request.client.host) if request.client else None
    if not direct_ip:
        return "unknown"

    trusted_proxies = {
        parsed
        for value in _parse_csv_config(auth_provider_config.oidc_trusted_proxy_ips)
        if (parsed := _parse_ip(value)) is not None
    }
    client_ip_headers = _parse_csv_config(auth_provider_config.oidc_client_ip_headers)

    # Only trust forwarding headers when request originates from a trusted proxy.
    if direct_ip in trusted_proxies:
        for header_name in client_ip_headers:
            raw_header_value = request.headers.get(header_name)
            if not raw_header_value:
                continue

            header_candidate = raw_header_value.split(",")[0].strip()
            parsed_ip = _parse_ip(header_candidate)
            if parsed_ip:
                return parsed_ip

    return direct_ip


async def _consume_oidc_auth_context(redis: ArqRedis, state: str) -> tuple[str, str]:
    """
    Validate state and atomically consume state+nonce+PKCE verifier in Redis.

    Returns:
        Tuple of (nonce, code_verifier).
    """
    state_key = RedisKeys.oidc_state(state)
    nonce_key = RedisKeys.oidc_nonce(state)
    code_verifier_key = RedisKeys.oidc_pkce_verifier(state)

    pipe = redis.pipeline(transaction=True)
    pipe.exists(state_key)
    pipe.get(nonce_key)
    pipe.get(code_verifier_key)
    pipe.delete(state_key)
    pipe.delete(nonce_key)
    pipe.delete(code_verifier_key)
    state_valid, nonce, code_verifier, _, _, _ = await pipe.execute()

    if not state_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired state"
        )
    if not nonce:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired nonce"
        )
    if isinstance(nonce, bytes):
        nonce = nonce.decode("utf-8")

    if not code_verifier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired PKCE verifier",
        )
    if isinstance(code_verifier, bytes):
        code_verifier = code_verifier.decode("utf-8")

    return str(nonce), str(code_verifier)


async def _enforce_oidc_rate_limit(
    redis: ArqRedis, request: Request, action: str, limit: int
) -> None:
    """Apply Redis-backed fixed-window rate limiting for OIDC endpoints."""
    client_id = _get_client_identifier(request)
    key = RedisKeys.oidc_rate_limit(action, client_id)
    current_count = await redis.incr(key)

    if current_count == 1:
        from glean_core.config import auth_provider_config

        await redis.expire(key, auth_provider_config.oidc_rate_limit_window_seconds)

    if current_count > limit:
        retry_after = await redis.ttl(key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
            headers={"Retry-After": str(max(retry_after, 1))},
        )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    config_service: Annotated[TypedConfigService, Depends(get_typed_config_service)],
) -> dict[str, UserResponse | TokenResponse]:
    """
    Register a new user account.

    Args:
        data: User registration data.
        auth_service: Authentication service.
        config_service: Typed config service.

    Returns:
        User profile and authentication tokens.

    Raises:
        HTTPException: If email is already registered or registration is disabled.
    """
    if not await config_service.is_registration_enabled():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is currently disabled by the administrator",
        )

    try:
        user, tokens = await auth_service.register(data)
        return {"user": user, "tokens": tokens}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None


@router.post("/login")
async def login(
    data: LoginRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> dict[str, UserResponse | TokenResponse]:
    """
    Authenticate user and issue tokens.

    Args:
        data: User login credentials.
        auth_service: Authentication service.

    Returns:
        User profile and authentication tokens.

    Raises:
        HTTPException: If credentials are invalid.
    """
    try:
        user, tokens = await auth_service.login(data)
        return {"user": user, "tokens": tokens}
    except ValueError as e:
        logger.info("Login failed", extra={"error_type": type(e).__name__})
        raise _authentication_failed_exception() from None


@router.post("/refresh")
async def refresh_token(
    data: RefreshTokenRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    """
    Refresh access token using refresh token.

    Args:
        data: Refresh token request.
        auth_service: Authentication service.

    Returns:
        New access and refresh tokens.

    Raises:
        HTTPException: If refresh token is invalid or expired.
    """
    try:
        tokens = await auth_service.refresh_access_token(data.refresh_token)
        return tokens
    except ValueError as e:
        logger.info("Token refresh failed", extra={"error_type": type(e).__name__})
        raise _authentication_failed_exception() from None


@router.post("/logout")
async def logout() -> dict[str, str]:
    """
    Logout user (placeholder for token invalidation).

    Returns:
        Success message.
    """
    # In a production system, you might want to invalidate the refresh token
    # by storing it in Redis with an expiration
    return {"message": "Logged out successfully"}


class AuthProvidersResponse(BaseModel):
    """Public authentication methods available on this server."""

    oidc_enabled: bool


@router.get("/providers", response_model=AuthProvidersResponse)
async def get_auth_providers() -> AuthProvidersResponse:
    """Return which external sign-in methods are enabled.

    The login page uses this to hide SSO when OIDC is not configured.
    """
    from glean_core.config import auth_provider_config

    return AuthProvidersResponse(oidc_enabled=auth_provider_config.oidc_enabled)


@router.get("/me")
async def get_me(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> UserResponse:
    """
    Get current authenticated user information.

    Args:
        current_user: Current authenticated user from token.

    Returns:
        User profile data.
    """
    return current_user


@router.patch("/me")
async def update_me(
    data: UserUpdate,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """
    Update current user profile and settings.

    Args:
        data: Update data (name, avatar_url, settings).
        current_user: Current authenticated user from token.
        user_service: User service.

    Returns:
        Updated user profile data.
    """
    return await user_service.update_user(current_user.id, data)


# OAuth/OIDC endpoints


@router.get("/oauth/oidc/authorize")
async def oidc_authorize(
    request: Request,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    redis: Annotated[ArqRedis, Depends(get_redis_pool)],
):
    """
    Get OIDC authorization URL.

    Args:
        auth_service: Authentication service.
        redis: Redis connection pool for state storage.

    Returns:
        authorization_url: URL to redirect user to OIDC provider.
        state: CSRF protection token.

    Raises:
        HTTPException: If OIDC is not enabled or provider not configured.
    """
    from secrets import token_urlsafe

    from glean_core.auth.providers import AuthProviderFactory, OIDCProvider
    from glean_core.config import auth_provider_config

    # Check if OIDC is enabled
    if not auth_provider_config.oidc_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="OIDC authentication is not enabled"
        )

    await _enforce_oidc_rate_limit(
        redis, request, "authorize", auth_provider_config.oidc_authorize_rate_limit
    )

    # Get OIDC provider config
    provider_config = auth_service.provider_configs.get("oidc")
    if not provider_config:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OIDC provider not configured",
        )

    try:
        # Create OIDC provider
        provider = AuthProviderFactory.create("oidc", provider_config)
        oidc_provider = cast(OIDCProvider, provider)

        # Load OIDC discovery config before generating authorization URL.
        await oidc_provider.prepare()

        # Generate CSRF state, nonce, and PKCE verifier/challenge
        state = token_urlsafe(32)
        nonce = token_urlsafe(32)
        code_verifier, code_challenge = oidc_provider.generate_pkce_pair()

        # Store state in Redis with 5-minute TTL for verification in callback
        await redis.setex(
            RedisKeys.oidc_state(state),
            RedisKeys.OIDC_STATE_TTL,
            "1",
        )

        # Store nonce in Redis for verification during token validation
        await redis.setex(
            RedisKeys.oidc_nonce(state),
            RedisKeys.OIDC_NONCE_TTL,
            nonce,
        )
        await redis.setex(
            RedisKeys.oidc_pkce_verifier(state),
            RedisKeys.OIDC_PKCE_VERIFIER_TTL,
            code_verifier,
        )

        # Get authorization URL with state, nonce, and PKCE challenge
        auth_url = oidc_provider.get_authorization_url(
            state=state,
            redirect_uri=str(provider_config["redirect_uri"]),
            nonce=nonce,
            code_challenge=code_challenge,
        )

        if not auth_url:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate authorization URL",
            )

        # Return response with no-cache headers to prevent browser caching
        return JSONResponse(
            content={
                "authorization_url": auth_url,
                "state": state,
            },
            headers=_oidc_no_cache_headers(),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("[OIDC] failed to generate authorization URL")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate authorization URL",
        ) from None


class OIDCCallbackRequest(BaseModel):
    """OIDC callback request payload."""

    code: str
    state: str


@router.post("/oauth/oidc/callback")
async def oidc_callback(
    request: Request,
    data: OIDCCallbackRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    redis: Annotated[ArqRedis, Depends(get_redis_pool)],
) -> JSONResponse:
    """
    Handle OIDC callback after user authorization.

    Args:
        data: OIDC callback data containing code and state.
        auth_service: Authentication service.
        redis: Redis connection pool for state validation.

    Returns:
        user: User profile.
        tokens: JWT access and refresh tokens.

    Raises:
        HTTPException: If authentication fails or provider not configured.
    """
    from glean_core.config import auth_provider_config

    if not auth_provider_config.oidc_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="OIDC authentication is not enabled"
        )

    await _enforce_oidc_rate_limit(
        redis, request, "callback", auth_provider_config.oidc_callback_rate_limit
    )

    nonce, code_verifier = await _consume_oidc_auth_context(redis, data.state)

    # Get provider config
    provider_config = auth_service.provider_configs.get("oidc")
    if not provider_config:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OIDC provider not configured",
        )

    # Prepare credentials with nonce for token verification
    credentials = {
        "code": data.code,
        "redirect_uri": str(provider_config["redirect_uri"]),
        "nonce": nonce,
        "code_verifier": code_verifier,
    }

    try:
        # Authenticate with OIDC provider
        user, tokens = await auth_service.login_with_provider("oidc", credentials)
        return JSONResponse(
            content={
                "user": user.model_dump(mode="json"),
                "tokens": tokens.model_dump(mode="json"),
            },
            headers=_oidc_no_cache_headers(),
        )
    except ValueError as e:
        logger.warning(
            "[OIDC] callback authentication failed",
            extra={"state_prefix": data.state[:8], "error_type": type(e).__name__},
        )
        raise _authentication_failed_exception() from None

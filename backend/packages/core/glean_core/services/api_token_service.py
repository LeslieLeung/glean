"""
API Token service.

Handles API token CRUD operations and verification for MCP authentication.
"""

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core.auth.password import hash_password, verify_password
from glean_core.schemas.api_token import (
    APITokenCreateResponse,
    APITokenListResponse,
    APITokenResponse,
)
from glean_database.models import APIToken


class APITokenService:
    """API Token management service."""

    def __init__(self, session: AsyncSession):
        """
        Initialize API token service.

        Args:
            session: Database session.
        """
        self.session = session

    async def create_token(
        self,
        user_id: str,
        name: str,
        expires_in_days: int | None = None,
    ) -> APITokenCreateResponse:
        """
        Create a new API token.

        Args:
            user_id: User identifier.
            name: Token name for identification.
            expires_in_days: Number of days until expiration (None = never expires).

        Returns:
            Created token response with plain token (only shown once).
        """
        # Generate token: glean_<32 random characters>
        plain_token = f"glean_{secrets.token_urlsafe(32)}"
        token_hash = hash_password(plain_token)
        token_prefix = plain_token[:12]  # "glean_xxxxxx"

        # Calculate expiration
        expires_at = None
        if expires_in_days:
            expires_at = datetime.now(UTC) + timedelta(days=expires_in_days)

        token = APIToken(
            user_id=user_id,
            name=name,
            token_hash=token_hash,
            token_prefix=token_prefix,
            expires_at=expires_at,
            is_revoked=False,
        )
        self.session.add(token)
        try:
            await self.session.commit()
            await self.session.refresh(token)
        except Exception:
            await self.session.rollback()
            raise

        return APITokenCreateResponse(
            id=token.id,
            name=token.name,
            token_prefix=token.token_prefix,
            token=plain_token,
            last_used_at=token.last_used_at,
            expires_at=token.expires_at,
            created_at=token.created_at,
        )

    async def verify_token(self, plain_token: str) -> APIToken | None:
        """
        Verify an API token and return the token record if valid.

        Args:
            plain_token: The plain text token to verify.

        Returns:
            APIToken record if valid, None otherwise.
        """
        # Check token format
        if not plain_token.startswith("glean_"):
            return None

        prefix = plain_token[:12]

        # Find tokens with matching prefix
        stmt = select(APIToken).where(
            APIToken.token_prefix == prefix,
            APIToken.is_revoked == False,  # noqa: E712
        )
        result = await self.session.execute(stmt)
        tokens = result.scalars().all()

        # Verify hash for each matching token
        # Use constant-time comparison to prevent timing attacks
        matched_token = None
        for token in tokens:
            if verify_password(plain_token, token.token_hash):
                # Check expiration
                if token.expires_at and token.expires_at < datetime.now(UTC):
                    # Store None if expired, but continue checking all tokens
                    pass
                elif matched_token is None:
                    # Only store the first valid match
                    matched_token = token

        return matched_token

    async def update_last_used(self, token_id: str) -> None:
        """
        Update the last_used_at timestamp for a token.

        Args:
            token_id: Token identifier.
        """
        stmt = (
            update(APIToken).where(APIToken.id == token_id).values(last_used_at=datetime.now(UTC))
        )
        try:
            await self.session.execute(stmt)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def list_tokens(self, user_id: str) -> APITokenListResponse:
        """
        List all tokens for a user.

        Args:
            user_id: User identifier.

        Returns:
            List of tokens (without hashes).
        """
        stmt = (
            select(APIToken)
            .where(APIToken.user_id == user_id, APIToken.is_revoked == False)  # noqa: E712
            .order_by(APIToken.created_at.desc())
        )
        result = await self.session.execute(stmt)
        tokens = result.scalars().all()

        return APITokenListResponse(
            tokens=[
                APITokenResponse(
                    id=token.id,
                    name=token.name,
                    token_prefix=token.token_prefix,
                    last_used_at=token.last_used_at,
                    expires_at=token.expires_at,
                    created_at=token.created_at,
                )
                for token in tokens
            ]
        )

    async def revoke_token(self, token_id: str, user_id: str) -> bool:
        """
        Revoke an API token.

        Args:
            token_id: Token identifier.
            user_id: User identifier for authorization.

        Returns:
            True if token was revoked, False if not found.

        Raises:
            ValueError: If token not found or unauthorized.
        """
        stmt = select(APIToken).where(APIToken.id == token_id, APIToken.user_id == user_id)
        result = await self.session.execute(stmt)
        token = result.scalar_one_or_none()

        if not token:
            raise ValueError("Token not found")

        token.is_revoked = True
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return True

    async def get_user_id_from_token(self, plain_token: str) -> str | None:
        """
        Get the user ID associated with a token.

        Args:
            plain_token: The plain text token.

        Returns:
            User ID if token is valid, None otherwise.
        """
        token = await self.verify_token(plain_token)
        if token:
            return token.user_id
        return None

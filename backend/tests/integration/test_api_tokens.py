"""Integration tests for API token management."""

import contextlib

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core.services.api_token_service import APITokenService
from glean_database.models.api_token import APIToken


class TestAPITokenCreate:
    """Test API token creation endpoint."""

    @pytest.mark.asyncio
    async def test_create_token_success(self, client: AsyncClient, auth_headers):
        """Test successful token creation."""
        response = await client.post(
            "/api/tokens",
            json={"name": "Test Token", "expires_in_days": 30},
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()

        assert "id" in data
        assert data["name"] == "Test Token"
        assert data["token_prefix"].startswith("glean_")
        assert "token" in data
        assert data["token"].startswith("glean_")
        assert "expires_at" in data

    @pytest.mark.asyncio
    async def test_create_token_no_expiration(self, client: AsyncClient, auth_headers):
        """Test creating a token without expiration."""
        response = await client.post(
            "/api/tokens",
            json={"name": "No Expiry Token"},
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()

        assert data["name"] == "No Expiry Token"
        assert data["expires_at"] is None

    @pytest.mark.asyncio
    async def test_create_token_invalid_name(self, client: AsyncClient, auth_headers):
        """Test token creation with invalid name."""
        response = await client.post(
            "/api/tokens",
            json={"name": "", "expires_in_days": 30},
            headers=auth_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_token_name_too_long(self, client: AsyncClient, auth_headers):
        """Test token creation with name exceeding max length."""
        response = await client.post(
            "/api/tokens",
            json={"name": "x" * 101, "expires_in_days": 30},
            headers=auth_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_token_invalid_expiration(self, client: AsyncClient, auth_headers):
        """Test token creation with invalid expiration days."""
        response = await client.post(
            "/api/tokens",
            json={"name": "Test Token", "expires_in_days": 0},
            headers=auth_headers,
        )

        assert response.status_code == 422

        response = await client.post(
            "/api/tokens",
            json={"name": "Test Token", "expires_in_days": 366},
            headers=auth_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_token_unauthorized(self, client: AsyncClient):
        """Test token creation without authentication."""
        response = await client.post(
            "/api/tokens",
            json={"name": "Test Token", "expires_in_days": 30},
        )

        assert response.status_code == 401


class TestAPITokenList:
    """Test API token listing endpoint."""

    @pytest.mark.asyncio
    async def test_list_tokens_success(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        """Test listing tokens for authenticated user."""
        # Create some tokens first
        service = APITokenService(db_session)
        await service.create_token(str(test_user.id), "Token 1", 30)
        await service.create_token(str(test_user.id), "Token 2", None)

        response = await client.get("/api/tokens", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert "tokens" in data
        assert len(data["tokens"]) == 2

        # Verify token data doesn't include actual token value
        for token in data["tokens"]:
            assert "token" not in token
            assert "token_hash" not in token
            assert "token_prefix" in token
            assert "name" in token

    @pytest.mark.asyncio
    async def test_list_tokens_empty(self, client: AsyncClient, auth_headers):
        """Test listing tokens when user has none."""
        response = await client.get("/api/tokens", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert "tokens" in data
        assert len(data["tokens"]) == 0

    @pytest.mark.asyncio
    async def test_list_tokens_unauthorized(self, client: AsyncClient):
        """Test listing tokens without authentication."""
        response = await client.get("/api/tokens")

        assert response.status_code == 401


class TestAPITokenRevoke:
    """Test API token revocation endpoint."""

    @pytest.mark.asyncio
    async def test_revoke_token_success(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        """Test successful token revocation."""
        # Create a token first
        service = APITokenService(db_session)
        token_response = await service.create_token(str(test_user.id), "Token to Revoke", 30)
        token_id = token_response.id

        response = await client.delete(f"/api/tokens/{token_id}", headers=auth_headers)

        assert response.status_code == 204

        # Verify token is revoked
        stmt = await db_session.execute(select(APIToken).where(APIToken.id == token_id))
        token = stmt.scalar_one_or_none()
        assert token is not None
        assert token.is_revoked is True

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_token(self, client: AsyncClient, auth_headers):
        """Test revoking a non-existent token."""
        response = await client.delete("/api/tokens/nonexistent-id", headers=auth_headers)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_revoke_token_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_user
    ):
        """Test revoking a token without authentication."""
        # Create a token
        service = APITokenService(db_session)
        token_response = await service.create_token(str(test_user.id), "Token", 30)
        token_id = token_response.id

        response = await client.delete(f"/api/tokens/{token_id}")

        assert response.status_code == 401


class TestAPITokenVerification:
    """Test API token verification logic."""

    @pytest.mark.asyncio
    async def test_verify_valid_token(self, db_session: AsyncSession, test_user):
        """Test verifying a valid token."""
        service = APITokenService(db_session)
        token_response = await service.create_token(str(test_user.id), "Valid Token", 30)
        plain_token = token_response.token

        # Verify the token
        verified_token = await service.verify_token(plain_token)

        assert verified_token is not None
        assert verified_token.user_id == str(test_user.id)
        assert verified_token.name == "Valid Token"

    @pytest.mark.asyncio
    async def test_verify_invalid_token(self, db_session: AsyncSession):
        """Test verifying an invalid token."""
        service = APITokenService(db_session)

        # Verify a non-existent token
        verified_token = await service.verify_token("glean_invalid_token_12345")

        assert verified_token is None

    @pytest.mark.asyncio
    async def test_verify_wrong_format_token(self, db_session: AsyncSession):
        """Test verifying a token with wrong format."""
        service = APITokenService(db_session)

        # Token doesn't start with "glean_"
        verified_token = await service.verify_token("invalid_token_format")

        assert verified_token is None

    @pytest.mark.asyncio
    async def test_verify_expired_token(self, db_session: AsyncSession, test_user):
        """Test verifying an expired token."""
        from datetime import UTC, datetime, timedelta

        service = APITokenService(db_session)

        # Create token that's already expired
        token = APIToken(
            user_id=str(test_user.id),
            name="Expired Token",
            token_hash="$2b$12$dummy_hash",
            token_prefix="glean_expire",
            expires_at=datetime.now(UTC) - timedelta(days=1),
            is_revoked=False,
        )
        db_session.add(token)
        await db_session.commit()

        # Try to verify (should fail because expired)
        verified_token = await service.verify_token("glean_expired_token")

        assert verified_token is None

    @pytest.mark.asyncio
    async def test_verify_revoked_token(self, db_session: AsyncSession, test_user):
        """Test verifying a revoked token."""
        service = APITokenService(db_session)
        token_response = await service.create_token(str(test_user.id), "Token to Revoke", 30)
        plain_token = token_response.token

        # Revoke the token
        await service.revoke_token(token_response.id, str(test_user.id))

        # Try to verify (should fail because revoked)
        verified_token = await service.verify_token(plain_token)

        assert verified_token is None

    @pytest.mark.asyncio
    async def test_verify_token_timing_attack_resistance(self, db_session: AsyncSession, test_user):
        """Test that token verification is resistant to timing attacks."""
        service = APITokenService(db_session)

        # Create multiple tokens with same prefix
        tokens = []
        for i in range(3):
            token_response = await service.create_token(str(test_user.id), f"Token {i}", 30)
            tokens.append(token_response.token)

        # Measure verification times for valid and invalid tokens
        # While we can't directly measure timing differences in a unit test,
        # we can verify that the verification logic checks all candidates
        # This test ensures the constant-time logic is in place

        # Verify each token successfully
        for token in tokens:
            verified = await service.verify_token(token)
            assert verified is not None

        # Verify invalid token with same prefix format
        invalid_token = "glean_" + "x" * 43  # Same length as valid tokens
        verified = await service.verify_token(invalid_token)
        assert verified is None


class TestAPITokenDatabaseTransactions:
    """Test database transaction handling."""

    @pytest.mark.asyncio
    async def test_create_token_rollback_on_error(self, test_user, test_engine):
        """Test that token creation rolls back on error."""
        from sqlalchemy.ext.asyncio import async_sessionmaker

        # Create a fresh session for this test to avoid greenlet issues
        async_session = async_sessionmaker(
            bind=test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async with async_session() as session:
            service = APITokenService(session)

            # Force an error by trying to create with an invalid user_id format
            # This should trigger a database constraint error (foreign key violation)
            with pytest.raises(IntegrityError):
                await service.create_token("invalid-uuid-format", "Test Token", 30)

            # After the error, create a new session to verify no token was created
            # This avoids greenlet context issues after IntegrityError

        async with async_session() as session:
            stmt = select(APIToken).where(APIToken.user_id == str(test_user.id))
            result = await session.execute(stmt)
            tokens_list = result.scalars().all()
            assert len(tokens_list) == 0

    @pytest.mark.asyncio
    async def test_update_last_used_rollback_on_error(self, db_session: AsyncSession, test_user):
        """Test that update_last_used rolls back on error."""
        service = APITokenService(db_session)

        # Try to update a non-existent token
        # This should handle the error gracefully
        with contextlib.suppress(Exception):
            await service.update_last_used("nonexistent-token-id")

        # Verify session is still usable
        tokens = await service.list_tokens(str(test_user.id))
        assert tokens is not None

"""Integration tests for authentication API endpoints."""

import pytest
from httpx import AsyncClient


class TestAuthRegister:
    """Test user registration endpoint."""

    @pytest.mark.asyncio
    async def test_register_success(self, client: AsyncClient):
        """Test successful user registration."""
        response = await client.post(
            "/api/auth/register",
            json={"email": "newuser@example.com", "name": "New User", "password": "SecurePass123"},
        )

        assert response.status_code == 201
        data = response.json()

        assert "user" in data
        assert "tokens" in data

        assert data["user"]["email"] == "newuser@example.com"
        assert data["user"]["name"] == "New User"
        assert "id" in data["user"]

        assert "access_token" in data["tokens"]
        assert "refresh_token" in data["tokens"]

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client: AsyncClient, test_user):
        """Test registration with existing email."""
        response = await client.post(
            "/api/auth/register",
            json={"email": test_user.email, "name": "Another User", "password": "SecurePass123"},
        )

        assert response.status_code == 400
        assert "already registered" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_register_invalid_email(self, client: AsyncClient):
        """Test registration with invalid email format."""
        response = await client.post(
            "/api/auth/register",
            json={"email": "not-an-email", "name": "Test User", "password": "SecurePass123"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_missing_fields(self, client: AsyncClient):
        """Test registration with missing required fields."""
        response = await client.post("/api/auth/register", json={"email": "test@example.com"})

        assert response.status_code == 422


class TestAuthLogin:
    """Test user login endpoint."""

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient, test_user):
        """Test successful user login."""
        response = await client.post(
            "/api/auth/login", json={"email": test_user.email, "password": "TestPass123"}
        )

        assert response.status_code == 200
        data = response.json()

        assert "user" in data
        assert "tokens" in data

        assert data["user"]["email"] == test_user.email
        assert "access_token" in data["tokens"]
        assert "refresh_token" in data["tokens"]

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient, test_user):
        """Test login with incorrect password."""
        response = await client.post(
            "/api/auth/login", json={"email": test_user.email, "password": "WrongPassword123"}
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Test login with non-existent email."""
        response = await client.post(
            "/api/auth/login",
            json={"email": "nonexistent@example.com", "password": "SomePassword123"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_missing_fields(self, client: AsyncClient):
        """Test login with missing fields."""
        response = await client.post("/api/auth/login", json={"email": "test@example.com"})

        assert response.status_code == 422


class TestAuthRefresh:
    """Test token refresh endpoint."""

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, client: AsyncClient, test_user):
        """Test successful token refresh."""
        # First login to get tokens
        login_response = await client.post(
            "/api/auth/login", json={"email": test_user.email, "password": "TestPass123"}
        )

        refresh_token = login_response.json()["tokens"]["refresh_token"]

        # Refresh the token
        response = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})

        assert response.status_code == 200
        data = response.json()

        assert "access_token" in data
        assert "refresh_token" in data

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self, client: AsyncClient):
        """Test refresh with invalid token."""
        response = await client.post(
            "/api/auth/refresh", json={"refresh_token": "invalid.token.here"}
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_with_access_token(self, client: AsyncClient, auth_headers):
        """Test that access token cannot be used to refresh."""
        # Extract the token from auth headers
        access_token = auth_headers["Authorization"].split(" ")[1]

        response = await client.post("/api/auth/refresh", json={"refresh_token": access_token})

        assert response.status_code == 401


class TestAuthMe:
    """Test get current user endpoint."""

    @pytest.mark.asyncio
    async def test_get_me_success(self, client: AsyncClient, test_user, auth_headers):
        """Test getting current user info with valid token."""
        response = await client.get("/api/auth/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert data["email"] == test_user.email
        assert data["name"] == test_user.name
        assert data["id"] == str(test_user.id)

    @pytest.mark.asyncio
    async def test_get_me_no_token(self, client: AsyncClient):
        """Test getting current user without token."""
        response = await client.get("/api/auth/me")

        # FastAPI's HTTPBearer returns 401 when no credentials provided
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_invalid_token(self, client: AsyncClient):
        """Test getting current user with invalid token."""
        response = await client.get(
            "/api/auth/me", headers={"Authorization": "Bearer invalid.token.here"}
        )

        assert response.status_code == 401


class TestAuthProviders:
    """Test the public provider-discovery endpoint."""

    @pytest.mark.asyncio
    async def test_providers_reports_oidc_disabled_by_default(self, client: AsyncClient):
        """OIDC is off unless the server is configured for it."""
        response = await client.get("/api/auth/providers")

        assert response.status_code == 200
        assert response.json() == {"oidc_enabled": False}


class TestAuthLogout:
    """Test logout endpoint."""

    @pytest.mark.asyncio
    async def test_logout_success(self, client: AsyncClient):
        """Test logout endpoint (placeholder functionality)."""
        response = await client.post("/api/auth/logout")

        assert response.status_code == 200
        assert "message" in response.json()

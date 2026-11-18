"""Account suspension must block every user authentication path."""

from contextlib import asynccontextmanager

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from glean_api.mcp.auth import APITokenVerifier
from glean_core.services import APITokenService
from glean_database.models import APIToken, User


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "body", "active_status"),
    [
        ("GET", "/api/auth/me", None, 200),
        ("PATCH", "/api/auth/me", {"name": "Updated profile"}, 200),
        ("POST", "/api/tokens", {"name": "Non-expiring token"}, 201),
    ],
)
async def test_disabled_user_cannot_use_existing_access_token(
    client: AsyncClient, test_user, auth_headers, admin_headers, method, path, body, active_status
) -> None:
    """An already-issued JWT must stop authorizing reads, writes, and token creation."""
    response = await client.request(method, path, headers=auth_headers, json=body)
    assert response.status_code == active_status

    response = await client.patch(
        f"/api/admin/users/{test_user.id}/status",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert response.status_code == 200

    response = await client.request(method, path, headers=auth_headers, json=body)
    assert response.status_code == 401
    assert response.json()["detail"] == "Account is disabled"
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_disabled_user_cannot_login_or_refresh(
    client: AsyncClient, test_user, admin_headers
) -> None:
    """Suspension also blocks password login and already-issued refresh tokens."""
    credentials = {"email": test_user.email, "password": "TestPass123"}
    login = await client.post("/api/auth/login", json=credentials)
    assert login.status_code == 200
    refresh_token = login.json()["tokens"]["refresh_token"]

    response = await client.patch(
        f"/api/admin/users/{test_user.id}/status",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert response.status_code == 200
    assert (await client.post("/api/auth/login", json=credentials)).status_code == 401
    response = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_disable_permanently_revokes_only_that_users_api_tokens(
    client: AsyncClient, db_session: AsyncSession, test_user, admin_headers
) -> None:
    """Disabling revokes all token types; enabling must not restore compromised tokens."""
    service = APITokenService(db_session)
    tokens = [
        await service.create_token(test_user.id, "No expiry"),
        await service.create_token(test_user.id, "Expires", 30),
        await service.create_token(test_user.id, "Already revoked"),
    ]
    await service.revoke_token(tokens[-1].id, test_user.id)
    other_user = User(email="other@example.com", is_active=True)
    db_session.add(other_user)
    await db_session.commit()
    other_token = await service.create_token(other_user.id, "Other user's token")

    for is_active in (False, False, True):
        response = await client.patch(
            f"/api/admin/users/{test_user.id}/status",
            headers=admin_headers,
            json={"is_active": is_active},
        )
        assert response.status_code == 200
        records = (
            (await db_session.execute(select(APIToken).where(APIToken.user_id == test_user.id)))
            .scalars()
            .all()
        )
        assert len(records) == 3
        assert all(token.is_revoked for token in records)
        for token in tokens:
            assert await service.verify_token(token.token) is None
        assert await service.verify_token(other_token.token) is not None

    login = await client.post(
        "/api/auth/login", json={"email": test_user.email, "password": "TestPass123"}
    )
    assert login.status_code == 200
    response = await client.post(
        "/api/tokens",
        json={"name": "New token after reactivation"},
        headers={"Authorization": f"Bearer {login.json()['tokens']['access_token']}"},
    )
    assert response.status_code == 201
    assert await service.verify_token(response.json()["token"]) is not None


@pytest.mark.asyncio
async def test_mcp_rejects_unrevoked_token_owned_by_disabled_user(
    client: AsyncClient, db_session: AsyncSession, test_user, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Legacy unrevoked tokens must fail at both the shared service and MCP boundary."""
    service = APITokenService(db_session)
    token = await service.create_token(test_user.id, "Legacy non-expiring token")

    @asynccontextmanager
    async def session_context():
        yield db_session

    monkeypatch.setattr("glean_api.mcp.auth.get_session_context", session_context)
    verifier = APITokenVerifier()
    verified = await verifier.verify_token(token.token)
    assert verified is not None
    assert verified.scopes == [f"user:{test_user.id}"]
    assert verified.expires_at is None

    # Simulate an account disabled before this fix, without revoking its tokens.
    test_user.is_active = False
    await db_session.commit()
    record = await db_session.get(APIToken, token.id)
    assert record is not None
    assert record.is_revoked is False

    assert await service.verify_token(token.token) is None
    assert await service.get_user_id_from_token(token.token) is None
    assert await verifier.verify_token(token.token) is None
    response = await client.post(
        "/mcp/mcp",
        headers={"Authorization": f"Bearer {token.token}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert response.status_code == 401

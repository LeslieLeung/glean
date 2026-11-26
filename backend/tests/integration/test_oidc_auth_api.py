"""Integration tests for OIDC authentication endpoints."""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from glean_api.dependencies import get_auth_service
from glean_api.main import app
from glean_core.schemas import TokenResponse, UserResponse


class _FakeOIDCProvider:
    async def prepare(self) -> None:
        return None

    @staticmethod
    def generate_pkce_pair() -> tuple[str, str]:
        return "code-verifier", "code-challenge"

    def get_authorization_url(
        self,
        state: str,
        redirect_uri: str,
        nonce: str | None = None,
        code_challenge: str | None = None,
    ) -> str:
        assert nonce is not None
        assert code_challenge is not None
        return (
            "https://issuer.example.com/oauth/authorize"
            f"?state={state}&redirect_uri={redirect_uri}&nonce={nonce}"
            f"&code_challenge={code_challenge}"
        )


class _FakeAuthService:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.provider_configs = {"oidc": {"redirect_uri": "http://localhost:3000/auth/callback"}}

    async def login_with_provider(
        self,
        provider_id: str,
        credentials: dict[str, str],
        *,
        allow_registration: bool = True,
    ):
        assert isinstance(allow_registration, bool)
        assert provider_id == "oidc"
        assert credentials["nonce"]
        assert credentials["code_verifier"]

        if self.should_fail:
            raise ValueError("Token verification failed")

        user = UserResponse(
            id="user-id",
            email="oidc@example.com",
            name="OIDC User",
            username=None,
            phone=None,
            avatar_url=None,
            is_active=True,
            is_verified=True,
            settings={},
            created_at=datetime.now(UTC),
            last_login_at=datetime.now(UTC),
        )
        tokens = TokenResponse(access_token="access-token", refresh_token="refresh-token")
        return user, tokens


@pytest.fixture
def _enable_oidc(monkeypatch: pytest.MonkeyPatch):
    from glean_core.config import auth_provider_config

    monkeypatch.setattr(auth_provider_config, "oidc_enabled", True)
    monkeypatch.setattr(auth_provider_config, "oidc_authorize_rate_limit", 30)
    monkeypatch.setattr(auth_provider_config, "oidc_callback_rate_limit", 30)
    monkeypatch.setattr(auth_provider_config, "oidc_rate_limit_window_seconds", 60)
    monkeypatch.setattr(auth_provider_config, "oidc_trusted_proxy_ips", "")
    monkeypatch.setattr(
        auth_provider_config, "oidc_client_ip_headers", "cf-connecting-ip,x-real-ip"
    )


@pytest.mark.asyncio
async def test_oidc_authorize_success(
    client: AsyncClient, test_mock_redis, monkeypatch: pytest.MonkeyPatch, _enable_oidc
) -> None:
    from glean_core.auth.providers import auth_factory

    app.dependency_overrides[get_auth_service] = lambda: _FakeAuthService()
    monkeypatch.setattr(
        auth_factory.AuthProviderFactory, "create", lambda *_args, **_kwargs: _FakeOIDCProvider()
    )

    response = await client.get("/api/auth/oauth/oidc/authorize")

    assert response.status_code == 200
    payload = response.json()
    assert "authorization_url" in payload
    assert payload["state"]
    assert payload["state_binding"]
    assert payload["state_binding"] != payload["state"]
    assert payload["state_binding"] not in payload["authorization_url"]
    assert response.headers["cache-control"].startswith("no-store")

    state = payload["state"]
    assert response.cookies.get("glean_oidc_state") == state
    assert test_mock_redis.has_key(f"oidc_state:{state}")
    assert test_mock_redis.has_key(f"oidc_state_binding:{state}")
    assert (await test_mock_redis.get(f"oidc_state_binding:{state}")) != payload["state_binding"]
    assert test_mock_redis.has_key(f"oidc_nonce:{state}")
    assert test_mock_redis.has_key(f"oidc_pkce_verifier:{state}")


@pytest.mark.asyncio
async def test_oidc_authorize_rate_limited(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, _enable_oidc
) -> None:
    from glean_core.auth.providers import auth_factory
    from glean_core.config import auth_provider_config

    monkeypatch.setattr(auth_provider_config, "oidc_authorize_rate_limit", 1)
    app.dependency_overrides[get_auth_service] = lambda: _FakeAuthService()
    monkeypatch.setattr(
        auth_factory.AuthProviderFactory, "create", lambda *_args, **_kwargs: _FakeOIDCProvider()
    )

    first = await client.get("/api/auth/oauth/oidc/authorize")
    second = await client.get("/api/auth/oauth/oidc/authorize")

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers["retry-after"]


@pytest.mark.asyncio
async def test_oidc_callback_rejects_invalid_state(client: AsyncClient, _enable_oidc) -> None:
    app.dependency_overrides[get_auth_service] = lambda: _FakeAuthService()

    response = await client.post(
        "/api/auth/oauth/oidc/callback",
        json={"code": "auth-code", "state": "missing-state"},
        cookies={"glean_oidc_state": "missing-state"},
    )

    assert response.status_code == 400
    assert "Invalid or expired state" in response.text


@pytest.mark.asyncio
async def test_oidc_callback_rejects_missing_or_mismatched_state_cookie(
    client: AsyncClient, test_mock_redis, _enable_oidc
) -> None:
    app.dependency_overrides[get_auth_service] = lambda: _FakeAuthService()
    test_mock_redis.seed("oidc_state:state-cookie", "1")
    test_mock_redis.seed("oidc_nonce:state-cookie", "nonce-cookie")
    test_mock_redis.seed("oidc_pkce_verifier:state-cookie", "code-verifier")

    missing_cookie = await client.post(
        "/api/auth/oauth/oidc/callback",
        json={"code": "auth-code", "state": "state-cookie"},
    )
    assert missing_cookie.status_code == 400
    assert "Invalid or missing OIDC state binding" in missing_cookie.text

    mismatch_cookie = await client.post(
        "/api/auth/oauth/oidc/callback",
        json={"code": "auth-code", "state": "state-cookie"},
        cookies={"glean_oidc_state": "different-state"},
    )
    assert mismatch_cookie.status_code == 400
    assert "Invalid or missing OIDC state binding" in mismatch_cookie.text
    # Ensure Redis state was NOT consumed when cookie binding failed
    assert test_mock_redis.has_key("oidc_state:state-cookie")


@pytest.mark.asyncio
async def test_oidc_callback_accepts_valid_state_binding_without_cookie(
    client: AsyncClient, test_mock_redis, monkeypatch: pytest.MonkeyPatch, _enable_oidc
) -> None:
    from glean_core.auth.providers import auth_factory

    app.dependency_overrides[get_auth_service] = lambda: _FakeAuthService()
    monkeypatch.setattr(
        auth_factory.AuthProviderFactory, "create", lambda *_args, **_kwargs: _FakeOIDCProvider()
    )

    auth_response = await client.get("/api/auth/oauth/oidc/authorize")
    assert auth_response.status_code == 200
    auth_payload = auth_response.json()

    # Packaged Electron file:// renderer sends cross-site POST with no SameSite=Lax cookie.
    client.cookies.clear()
    response = await client.post(
        "/api/auth/oauth/oidc/callback",
        json={
            "code": "auth-code",
            "state": auth_payload["state"],
            "state_binding": auth_payload["state_binding"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["email"] == "oidc@example.com"
    assert payload["tokens"]["access_token"] == "access-token"
    assert not test_mock_redis.has_key(f"oidc_state:{auth_payload['state']}")
    assert not test_mock_redis.has_key(f"oidc_state_binding:{auth_payload['state']}")

    # State binding cannot be replayed after consumption.
    replay = await client.post(
        "/api/auth/oauth/oidc/callback",
        json={
            "code": "auth-code",
            "state": auth_payload["state"],
            "state_binding": auth_payload["state_binding"],
        },
    )
    assert replay.status_code == 400


@pytest.mark.asyncio
async def test_oidc_callback_rejects_invalid_state_binding_even_with_valid_cookie(
    client: AsyncClient, test_mock_redis, _enable_oidc
) -> None:
    import hashlib

    app.dependency_overrides[get_auth_service] = lambda: _FakeAuthService()
    test_mock_redis.seed("oidc_state:state-bind-check", "1")
    test_mock_redis.seed("oidc_nonce:state-bind-check", "nonce-bind")
    test_mock_redis.seed("oidc_pkce_verifier:state-bind-check", "code-verifier")
    test_mock_redis.seed(
        "oidc_state_binding:state-bind-check",
        hashlib.sha256(b"real-binding-secret").hexdigest(),
    )

    response = await client.post(
        "/api/auth/oauth/oidc/callback",
        json={
            "code": "auth-code",
            "state": "state-bind-check",
            "state_binding": "forged-binding-secret",
        },
        cookies={"glean_oidc_state": "state-bind-check"},
    )

    assert response.status_code == 400
    assert "Invalid or missing OIDC state binding" in response.text
    assert test_mock_redis.has_key("oidc_state:state-bind-check")
    assert test_mock_redis.has_key("oidc_state_binding:state-bind-check")


@pytest.mark.asyncio
async def test_oidc_callback_rejects_missing_nonce(
    client: AsyncClient, test_mock_redis, _enable_oidc
) -> None:
    app.dependency_overrides[get_auth_service] = lambda: _FakeAuthService()
    test_mock_redis.seed("oidc_state:state-1", "1")
    test_mock_redis.seed("oidc_pkce_verifier:state-1", "code-verifier")

    response = await client.post(
        "/api/auth/oauth/oidc/callback",
        json={"code": "auth-code", "state": "state-1"},
        cookies={"glean_oidc_state": "state-1"},
    )

    assert response.status_code == 400
    assert "Invalid or expired nonce" in response.text


@pytest.mark.asyncio
async def test_oidc_callback_success(client: AsyncClient, test_mock_redis, _enable_oidc) -> None:
    app.dependency_overrides[get_auth_service] = lambda: _FakeAuthService()
    test_mock_redis.seed("oidc_state:state-2", "1")
    test_mock_redis.seed("oidc_nonce:state-2", "nonce-2")
    test_mock_redis.seed("oidc_pkce_verifier:state-2", "code-verifier")

    response = await client.post(
        "/api/auth/oauth/oidc/callback",
        json={"code": "auth-code", "state": "state-2"},
        cookies={"glean_oidc_state": "state-2"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["email"] == "oidc@example.com"
    assert payload["tokens"]["access_token"] == "access-token"
    assert not test_mock_redis.has_key("oidc_state:state-2")
    assert not test_mock_redis.has_key("oidc_nonce:state-2")
    assert not test_mock_redis.has_key("oidc_pkce_verifier:state-2")


@pytest.mark.asyncio
async def test_oidc_callback_auth_failure_returns_401(
    client: AsyncClient, test_mock_redis, _enable_oidc
) -> None:
    app.dependency_overrides[get_auth_service] = lambda: _FakeAuthService(should_fail=True)
    test_mock_redis.seed("oidc_state:state-3", "1")
    test_mock_redis.seed("oidc_nonce:state-3", "nonce-3")
    test_mock_redis.seed("oidc_pkce_verifier:state-3", "code-verifier")

    response = await client.post(
        "/api/auth/oauth/oidc/callback",
        json={"code": "auth-code", "state": "state-3"},
        cookies={"glean_oidc_state": "state-3"},
    )

    assert response.status_code == 401
    assert "Authentication failed. Please try again." in response.text


@pytest.mark.asyncio
async def test_oidc_callback_rate_limited(
    client: AsyncClient, test_mock_redis, monkeypatch: pytest.MonkeyPatch, _enable_oidc
) -> None:
    from glean_core.config import auth_provider_config

    app.dependency_overrides[get_auth_service] = lambda: _FakeAuthService()
    monkeypatch.setattr(auth_provider_config, "oidc_callback_rate_limit", 1)
    test_mock_redis.seed("oidc_state:state-4a", "1")
    test_mock_redis.seed("oidc_nonce:state-4a", "nonce-4a")
    test_mock_redis.seed("oidc_pkce_verifier:state-4a", "code-verifier")
    test_mock_redis.seed("oidc_state:state-4b", "1")
    test_mock_redis.seed("oidc_nonce:state-4b", "nonce-4b")
    test_mock_redis.seed("oidc_pkce_verifier:state-4b", "code-verifier")

    first = await client.post(
        "/api/auth/oauth/oidc/callback",
        json={"code": "auth-code", "state": "state-4a"},
        cookies={"glean_oidc_state": "state-4a"},
    )
    second = await client.post(
        "/api/auth/oauth/oidc/callback",
        json={"code": "auth-code", "state": "state-4b"},
        cookies={"glean_oidc_state": "state-4b"},
    )

    assert first.status_code == 200
    assert second.status_code == 429

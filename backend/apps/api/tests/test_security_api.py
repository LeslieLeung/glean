"""Security regression tests for API endpoints: auth, RBAC, config, MCP, and OPML."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from glean_api.config import Settings, settings, validate_runtime_security_settings
from glean_core.auth import JWTConfig, create_admin_access_token
from glean_core.schemas.config import EmbeddingConfig
from glean_core.services import AdminService, TypedConfigService
from glean_database.models.admin import AdminRole


class TestRuntimeSecurityValidation:
    """Tests for fail-closed SECRET_KEY startup validation."""

    @pytest.mark.parametrize(
        "secret",
        [
            "change-me-in-production",
            "change-me-in-production-use-a-long-random-string",
            "short-secret-key",
        ],
    )
    def test_rejects_placeholder_or_short_secret_in_production(self, secret: str) -> None:
        cfg = Settings(debug=False, secret_key=secret)
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            validate_runtime_security_settings(cfg)

    def test_accepts_strong_secret_or_debug_mode(self) -> None:
        validate_runtime_security_settings(Settings(debug=True, secret_key="short"))
        validate_runtime_security_settings(Settings(debug=False, secret_key="a" * 32))


@pytest.mark.asyncio
class TestAuthRotationRateLimitAndFlags:
    """Tests for refresh-token rotation/revocation, login flags, and rate limiting."""

    async def test_refresh_token_rotation_and_logout_revocation(self, client: AsyncClient) -> None:
        reg = await client.post(
            "/api/auth/register",
            json={
                "email": "rotate@example.com",
                "name": "Rotate User",
                "password": "Password123!",
            },
        )
        assert reg.status_code == 201
        refresh_1 = reg.json()["tokens"]["refresh_token"]

        refreshed = await client.post("/api/auth/refresh", json={"refresh_token": refresh_1})
        assert refreshed.status_code == 200
        refresh_2 = refreshed.json()["refresh_token"]
        assert refresh_2 != refresh_1

        # Replaying rotated refresh_1 must be rejected
        replay = await client.post("/api/auth/refresh", json={"refresh_token": refresh_1})
        assert replay.status_code == 401

        # Explicitly logging out revokes refresh_2
        logout = await client.post("/api/auth/logout", json={"refresh_token": refresh_2})
        assert logout.status_code == 200

        after_logout = await client.post("/api/auth/refresh", json={"refresh_token": refresh_2})
        assert after_logout.status_code == 401

    async def test_local_auth_provider_flags_enforced(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from glean_core.config import auth_provider_config

        monkeypatch.setattr(auth_provider_config, "local_allow_registration", False)
        reg = await client.post(
            "/api/auth/register",
            json={"email": "blocked@example.com", "name": "Blocked", "password": "Password123!"},
        )
        assert reg.status_code == 403

        monkeypatch.setattr(auth_provider_config, "local_enabled", False)
        login = await client.post(
            "/api/auth/login",
            json={"email": "blocked@example.com", "password": "Password123!"},
        )
        assert login.status_code == 403

    async def test_login_rate_limited(self, client: AsyncClient) -> None:
        for _ in range(10):
            resp = await client.post(
                "/api/auth/login",
                json={"email": "nobody@example.com", "password": "wrongpassword"},
            )
            assert resp.status_code == 401

        limited = await client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "wrongpassword"},
        )
        assert limited.status_code == 429
        assert "retry-after" in limited.headers

    async def test_login_rate_limit_isolated_per_client_behind_trusted_proxy(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from glean_core.config import auth_provider_config

        monkeypatch.setattr(
            auth_provider_config, "oidc_trusted_proxy_ips", "127.0.0.1,172.16.0.0/12"
        )
        monkeypatch.setattr(auth_provider_config, "oidc_client_ip_headers", "x-real-ip")

        for _ in range(10):
            resp = await client.post(
                "/api/auth/login",
                json={"email": "nobody@example.com", "password": "wrongpassword"},
                headers={"X-Real-IP": "203.0.113.10"},
            )
            assert resp.status_code == 401

        blocked = await client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "wrongpassword"},
            headers={"X-Real-IP": "203.0.113.10"},
        )
        assert blocked.status_code == 429

        other_client = await client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "wrongpassword"},
            headers={"X-Real-IP": "198.51.100.20"},
        )
        assert other_client.status_code == 401


class TestClientIdentifierTrustedProxies:
    """Tests for CIDR matching and forwarded header selection in _get_client_identifier."""

    def test_client_identifier_cidr_and_forwarded_header_handling(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from starlette.requests import Request

        from glean_api.routers.auth import _get_client_identifier
        from glean_core.config import auth_provider_config

        def _make_request(client_host: str, headers: dict[str, str] | None = None) -> Request:
            raw_headers = [
                (k.lower().encode("latin-1"), v.encode("latin-1"))
                for k, v in (headers or {}).items()
            ]
            scope = {
                "type": "http",
                "method": "POST",
                "path": "/api/auth/login",
                "headers": raw_headers,
                "client": (client_host, 12345),
            }
            return Request(scope)

        # Matches Docker bridge CIDR and reads nginx's X-Real-IP
        monkeypatch.setattr(auth_provider_config, "oidc_trusted_proxy_ips", "172.16.0.0/12")
        monkeypatch.setattr(auth_provider_config, "oidc_client_ip_headers", "x-real-ip")
        assert (
            _get_client_identifier(
                _make_request(
                    "172.18.0.4",
                    {"X-Real-IP": "203.0.113.5", "CF-Connecting-IP": "198.51.100.99"},
                )
            )
            == "203.0.113.5"
        )
        # Unwraps IPv4-mapped IPv6 proxy socket addresses
        assert (
            _get_client_identifier(_make_request("::ffff:172.18.0.4", {"X-Real-IP": "203.0.113.6"}))
            == "203.0.113.6"
        )

        # Default header setting ignores spoofed CF-Connecting-IP when X-Real-IP is absent
        assert (
            _get_client_identifier(
                _make_request("172.18.0.4", {"CF-Connecting-IP": "198.51.100.99"})
            )
            == "172.18.0.4"
        )

        # Untrusted direct client IP ignores forwarding headers
        assert (
            _get_client_identifier(_make_request("198.51.100.40", {"X-Real-IP": "203.0.113.7"}))
            == "198.51.100.40"
        )
        monkeypatch.setattr(auth_provider_config, "oidc_trusted_proxy_ips", "")
        assert (
            _get_client_identifier(_make_request("172.18.0.4", {"X-Real-IP": "203.0.113.8"}))
            == "172.18.0.4"
        )

        # X-Forwarded-For picks rightmost non-trusted hop and prevents leftmost spoofing
        monkeypatch.setattr(
            auth_provider_config, "oidc_trusted_proxy_ips", "172.16.0.0/12,10.0.0.0/8"
        )
        monkeypatch.setattr(auth_provider_config, "oidc_client_ip_headers", "x-forwarded-for")
        assert (
            _get_client_identifier(
                _make_request(
                    "172.18.0.4",
                    {"X-Forwarded-For": "198.51.100.1, 203.0.113.10, 10.0.0.5"},
                )
            )
            == "203.0.113.10"
        )
        # If every hop is a private/trusted LAN address, falls back to the original client IP
        assert (
            _get_client_identifier(
                _make_request("172.18.0.4", {"X-Forwarded-For": "10.0.0.9, 172.18.0.2"})
            )
            == "10.0.0.9"
        )


@pytest.mark.asyncio
class TestAdminRBACRotationAndEmbeddingGuard:
    """Tests for admin JWT rotation, password change, super_admin RBAC, and embedding guards."""

    async def test_admin_refresh_rotation_logout_and_password_change(
        self, client: AsyncClient, admin_user, db_session: AsyncSession
    ) -> None:
        login = await client.post(
            "/api/admin/auth/login",
            json={"username": "admin_test", "password": "Admin123!"},
        )
        assert login.status_code == 200
        access = login.json()["access_token"]
        refresh_1 = login.json()["refresh_token"]

        rot = await client.post("/api/admin/auth/refresh", json={"refresh_token": refresh_1})
        assert rot.status_code == 200
        refresh_2 = rot.json()["refresh_token"]

        replay = await client.post("/api/admin/auth/refresh", json={"refresh_token": refresh_1})
        assert replay.status_code == 401
        assert replay.json()["detail"] == "Invalid refresh token"

        # Change admin password
        bad_pw = await client.post(
            "/api/admin/auth/change-password",
            json={"current_password": "wrong-password", "new_password": "NewStrongPass123!"},
            headers={"Authorization": f"Bearer {access}"},
        )
        assert bad_pw.status_code == 400

        ok_pw = await client.post(
            "/api/admin/auth/change-password",
            json={"current_password": "Admin123!", "new_password": "NewStrongPass123!"},
            headers={"Authorization": f"Bearer {access}"},
        )
        assert ok_pw.status_code == 200

        # Logout revokes admin refresh token
        logout = await client.post("/api/admin/auth/logout", json={"refresh_token": refresh_2})
        assert logout.status_code == 200
        revoked = await client.post("/api/admin/auth/refresh", json={"refresh_token": refresh_2})
        assert revoked.status_code == 401

    async def test_regular_admin_denied_super_admin_routes(
        self, client: AsyncClient, db_session: AsyncSession, test_user
    ) -> None:
        admin_service = AdminService(db_session)
        sub_admin = await admin_service.create_admin_user(
            username=f"sub_admin_{uuid4().hex[:6]}",
            password="StrongSubAdminPass123!",
            role=AdminRole.ADMIN,
        )
        await db_session.commit()

        jwt_cfg = JWTConfig(secret_key=settings.secret_key, algorithm=settings.jwt_algorithm)
        sub_token = create_admin_access_token(
            sub_admin.id, sub_admin.username, AdminRole.ADMIN.value, jwt_cfg
        )
        headers = {"Authorization": f"Bearer {sub_token}"}

        # Regular admin can read stats
        assert (await client.get("/api/admin/stats", headers=headers)).status_code == 200

        # Privileged routes require super_admin
        assert (
            await client.patch(
                f"/api/admin/users/{test_user.id}/status",
                json={"is_active": False},
                headers=headers,
            )
        ).status_code == 403
        assert (
            await client.post(
                "/api/admin/feeds/batch",
                json={"action": "disable", "feed_ids": []},
                headers=headers,
            )
        ).status_code == 403
        assert (
            await client.post("/api/admin/settings/registration?enabled=false", headers=headers)
        ).status_code == 403
        assert (
            await client.put(
                "/api/admin/embedding/config",
                json={"dimension": 1536},
                headers=headers,
            )
        ).status_code == 403

    async def test_embedding_config_rejects_base_url_switch_without_new_api_key(
        self, client: AsyncClient, admin_headers, db_session: AsyncSession
    ) -> None:
        cfg_service = TypedConfigService(db_session)
        await cfg_service.update(
            EmbeddingConfig,
            provider="openai",
            model="text-embedding-3-small",
            dimension=1536,
            api_key="sk-existing-secret",
            base_url="https://api.openai.com/v1",
        )
        await db_session.commit()

        resp = await client.put(
            "/api/admin/embedding/config",
            json={"base_url": "https://attacker.example.com/v1"},
            headers=admin_headers,
        )
        assert resp.status_code == 400
        assert "new api_key" in resp.json()["detail"]


@pytest.mark.asyncio
class TestSystemMcpAndOpmlHardening:
    """Tests for system endpoint auth, MCP DNS rebinding host checks, OPML limits, and logging."""

    async def test_vectorization_status_requires_authentication(self, client: AsyncClient) -> None:
        resp = await client.get("/api/system/vectorization-status")
        assert resp.status_code in (401, 403)

    async def test_opml_import_rejects_oversized_or_overcount(
        self, client: AsyncClient, auth_headers
    ) -> None:
        huge = b"a" * (2 * 1024 * 1024 + 64)
        resp_huge = await client.post(
            "/api/feeds/import",
            headers=auth_headers,
            files={"file": ("subs.opml", huge, "application/xml")},
        )
        assert resp_huge.status_code == 413

        outlines = "\n".join(
            f'<outline text="F{i}" xmlUrl="https://example.com/f{i}.xml"/>' for i in range(501)
        )
        many_opml = f'<?xml version="1.0"?><opml version="2.0"><body>{outlines}</body></opml>'
        resp_many = await client.post(
            "/api/feeds/import",
            headers=auth_headers,
            files={"file": ("many.opml", many_opml.encode("utf-8"), "application/xml")},
        )
        assert resp_many.status_code == 400
        assert "500" in resp_many.json()["detail"]

    async def test_mcp_transport_security_rejects_dns_rebinding_host(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from httpx import ASGITransport
        from mcp.server.auth.provider import AccessToken

        from glean_api.mcp.auth import APITokenVerifier
        from glean_api.mcp.server import create_mcp_server

        async def _fake_verify_token(_self: APITokenVerifier, token: str) -> AccessToken:
            return AccessToken(
                token=token,
                client_id="glean-mcp",
                scopes=["user:test-user"],
            )

        monkeypatch.setattr(APITokenVerifier, "verify_token", _fake_verify_token)

        mcp_server = create_mcp_server()
        assert mcp_server.settings.transport_security is not None
        assert mcp_server.settings.transport_security.enable_dns_rebinding_protection is True
        mcp_http_app = mcp_server.streamable_http_app()

        async with (
            mcp_server.session_manager.run(),
            AsyncClient(
                transport=ASGITransport(app=mcp_http_app),
                base_url="http://localhost:8000",
            ) as mcp_client,
        ):
            payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
            blocked_host = await mcp_client.post(
                "/mcp",
                headers={
                    "Authorization": "Bearer test-mcp-token",
                    "Host": "evil.attacker:8000",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            assert blocked_host.status_code == 421

            blocked_origin = await mcp_client.post(
                "/mcp",
                headers={
                    "Authorization": "Bearer test-mcp-token",
                    "Host": "localhost:8000",
                    "Origin": "https://evil.attacker",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            assert blocked_origin.status_code == 403

            allowed = await mcp_client.post(
                "/mcp",
                headers={
                    "Authorization": "Bearer test-mcp-token",
                    "Host": "localhost:8000",
                    "Origin": "http://localhost:5173",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            assert allowed.status_code not in (401, 403, 421)

    async def test_mcp_transport_security_allows_configured_remote_hosts_and_origins(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from httpx import ASGITransport
        from mcp.server.auth.provider import AccessToken

        from glean_api.mcp.auth import APITokenVerifier
        from glean_api.mcp.server import create_mcp_server

        async def _fake_verify_token(_self: APITokenVerifier, token: str) -> AccessToken:
            return AccessToken(
                token=token,
                client_id="glean-mcp",
                scopes=["user:test-user"],
            )

        monkeypatch.setattr(APITokenVerifier, "verify_token", _fake_verify_token)
        monkeypatch.setattr(settings, "mcp_allowed_hosts", "glean.example.com,192.168.1.10:8080")
        monkeypatch.setattr(settings, "mcp_resource_server_url", "https://mcp.example.com/mcp")

        mcp_server = create_mcp_server()
        mcp_http_app = mcp_server.streamable_http_app()

        async with (
            mcp_server.session_manager.run(),
            AsyncClient(
                transport=ASGITransport(app=mcp_http_app),
                base_url="https://glean.example.com",
            ) as mcp_client,
        ):
            payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}

            for headers in (
                {
                    "Authorization": "Bearer test-mcp-token",
                    "Host": "glean.example.com",
                    "Content-Type": "application/json",
                },
                {
                    "Authorization": "Bearer test-mcp-token",
                    "Host": "glean.example.com",
                    "Origin": "https://glean.example.com",
                    "Content-Type": "application/json",
                },
                {
                    "Authorization": "Bearer test-mcp-token",
                    "Host": "192.168.1.10:8080",
                    "Origin": "http://192.168.1.10:8080",
                    "Content-Type": "application/json",
                },
                {
                    "Authorization": "Bearer test-mcp-token",
                    "Host": "mcp.example.com",
                    "Origin": "https://mcp.example.com",
                    "Content-Type": "application/json",
                },
            ):
                allowed = await mcp_client.post("/mcp", headers=headers, json=payload)
                assert allowed.status_code not in (401, 403, 421)

            blocked_host = await mcp_client.post(
                "/mcp",
                headers={
                    "Authorization": "Bearer test-mcp-token",
                    "Host": "evil.attacker",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            assert blocked_host.status_code == 421

            blocked_origin = await mcp_client.post(
                "/mcp",
                headers={
                    "Authorization": "Bearer test-mcp-token",
                    "Host": "glean.example.com",
                    "Origin": "https://evil.attacker",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            assert blocked_origin.status_code == 403

    async def test_logging_middleware_strips_query_string(self, client: AsyncClient) -> None:
        from glean_core.logging_config import logger as core_logger

        records: list[dict[str, object]] = []

        def sink(message) -> None:
            record = message.record
            records.append({"msg": record["message"], "extra": dict(record["extra"])})

        handler_id = core_logger.add(sink)
        try:
            await client.get("/api/health?token=secret-query-value")
        finally:
            core_logger.remove(handler_id)

        assert any(
            isinstance(item.get("extra"), dict)
            and item["extra"].get("url") == "/api/health"
            and "secret-query-value" not in str(item)
            for item in records
        )


class TestProductionComposeSecurityEnv:
    """Tests ensuring production Compose files pass security and MCP env vars."""

    def test_production_compose_wires_mcp_and_security_env_vars(self) -> None:
        from typing import Any, cast

        import yaml  # type: ignore[import-untyped]

        repo_root = Path(__file__).resolve().parents[4]
        required_backend_vars = {
            "MCP_ALLOWED_HOSTS",
            "MCP_RESOURCE_SERVER_URL",
            "MCP_ISSUER_URL",
            "CORS_ORIGINS",
            "LOG_DIAGNOSE",
            "GLEAN_EMBEDDING_ALLOW_PRIVATE",
        }
        for compose_name in ("docker-compose.yml", "docker-compose.pgvector.yml"):
            raw = yaml.safe_load((repo_root / compose_name).read_text(encoding="utf-8"))
            parsed = cast(dict[str, Any], raw)
            backend_env = cast(dict[str, Any], parsed["services"]["backend"]["environment"])
            missing = required_backend_vars - backend_env.keys()
            assert not missing, f"{compose_name} missing backend env vars: {missing}"

    def test_backend_entrypoint_migrates_log_volume_before_dropping_root(self) -> None:
        repo_root = Path(__file__).resolve().parents[4]
        dockerfile = (repo_root / "backend" / "Dockerfile").read_text(encoding="utf-8")
        entrypoint = (repo_root / "backend" / "scripts" / "entrypoint.sh").read_text(
            encoding="utf-8"
        )

        assert "appuser" in dockerfile
        assert "mkdir -p /app/logs" in dockerfile
        assert 'ENTRYPOINT ["/app/scripts/entrypoint.sh"]' in dockerfile
        assert "USER appuser" not in dockerfile

        drop_idx = entrypoint.index("exec setpriv")
        chown_idx = entrypoint.index("chown -Rh appuser:appuser /app/logs")
        migrate_idx = entrypoint.index("alembic upgrade head")
        cmd_idx = entrypoint.index('exec "$@"')

        assert '[ "$(id -u)" -eq 0 ]' in entrypoint
        assert chown_idx < drop_idx < migrate_idx < cmd_idx
        for flag in ("--reuid", "--regid", "--init-groups", "--no-new-privs"):
            assert flag in entrypoint

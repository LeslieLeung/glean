"""Unit/integration-style tests for OIDC paths in AuthService."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from glean_core.auth import JWTConfig
from glean_core.services.auth_service import AuthService
from glean_database.models import User, UserAuthProvider


class _FakeProvider:
    async def authenticate(self, _credentials: dict[str, str]) -> dict[str, object]:
        return {
            "user_info": {"sub": "oidc-user-123"},
            "provider_user_id": "oidc-user-123",
            "email": "oidc.user@example.com",
            "name": "OIDC User",
            "username": "oidc-user",
            "phone": None,
            "avatar_url": "https://example.com/avatar.png",
            "metadata": {"email_verified": True},
        }


def _jwt_config() -> JWTConfig:
    return JWTConfig(secret_key="test-secret-key" + "0" * 32, algorithm="HS256")


@pytest.mark.asyncio
@pytest.mark.parametrize("has_mapping", [False, True])
async def test_login_with_provider_rejects_disabled_user(
    db_session, monkeypatch: pytest.MonkeyPatch, has_mapping: bool
) -> None:
    """Neither existing provider mappings nor email linking may bypass suspension."""
    user = User(email="oidc.user@example.com", is_active=False)
    db_session.add(user)
    await db_session.flush()
    if has_mapping:
        db_session.add(
            UserAuthProvider(
                user_id=user.id,
                provider_id="oidc",
                provider_user_id="oidc-user-123",
            )
        )
    await db_session.commit()

    monkeypatch.setattr(
        "glean_core.auth.providers.auth_factory.AuthProviderFactory.create",
        lambda *_args, **_kwargs: _FakeProvider(),
    )
    service = AuthService(db_session, _jwt_config(), provider_configs={"oidc": {"enabled": True}})

    with pytest.raises(ValueError, match="Account is disabled"):
        await service.login_with_provider("oidc", {"code": "valid-code"})
    assert user.last_login_at is None


@pytest.mark.asyncio
async def test_login_with_provider_creates_user_and_mapping(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = AuthService(
        db_session,
        _jwt_config(),
        provider_configs={
            "oidc": {
                "client_id": "id",
                "client_secret": "secret",
                "issuer": "https://issuer.example.com",
                "redirect_uri": "http://localhost/callback",
            }
        },
    )

    from glean_core.auth.providers import auth_factory

    monkeypatch.setattr(
        auth_factory.AuthProviderFactory, "create", lambda *_args, **_kwargs: _FakeProvider()
    )

    user, tokens = await service.login_with_provider(
        "oidc",
        {"code": "code", "redirect_uri": "http://localhost/callback", "nonce": "nonce"},
    )

    assert user.email == "oidc.user@example.com"
    assert user.is_verified is True
    assert tokens.access_token
    assert tokens.refresh_token

    providers = (
        (
            await db_session.execute(
                select(UserAuthProvider).where(UserAuthProvider.user_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(providers) == 1


@pytest.mark.asyncio
async def test_find_or_create_oauth_user_retries_after_integrity_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Result:
        def scalar_one_or_none(self):
            return None

        def scalars(self):
            return self

        def first(self):
            return None

    class _FakeSession:
        async def execute(self, _stmt):
            return _Result()

        def add(self, _obj) -> None:
            return None

        async def flush(self) -> None:
            raise IntegrityError("insert", {}, Exception("duplicate"))

        async def rollback(self) -> None:
            return None

    session = _FakeSession()
    service = AuthService(session, _jwt_config())
    auth_result = {
        "user_info": {"sub": "provider-user"},
        "provider_user_id": "provider-user",
        "email": "race@example.com",
        "name": "Race User",
        "username": None,
        "phone": None,
        "avatar_url": None,
        "metadata": {"email_verified": True},
    }

    # No existing user on initial lookups, then flush fails, then retry finds user.
    existing_user = User(
        id="user-id",
        email="race@example.com",
        name="Race User",
        password_hash=None,
        primary_auth_provider="oidc",
        provider_user_id="provider-user",
        is_active=True,
        is_verified=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    retry_results = iter([None, None, existing_user])

    async def _find_existing(*_args, **_kwargs):
        return next(retry_results)

    service._find_existing_oauth_user = _find_existing  # type: ignore[method-assign]

    sleep_calls: list[float] = []

    async def _fake_sleep(duration: float) -> None:
        sleep_calls.append(duration)

    monkeypatch.setattr("glean_core.services.auth_service.asyncio.sleep", _fake_sleep)

    user = await service._find_or_create_oauth_user("oidc", auth_result)

    assert user.id == "user-id"
    assert sleep_calls == [0.05, 0.05]


@pytest.mark.asyncio
async def test_find_or_create_oauth_user_links_existing_email(db_session) -> None:
    service = AuthService(db_session, _jwt_config())
    existing = User(
        email="shared@example.com",
        name="Existing User",
        password_hash=None,
        primary_auth_provider="oidc",
        provider_user_id="existing-provider-user",
        is_active=True,
        is_verified=True,
    )
    db_session.add(existing)
    await db_session.commit()
    await db_session.refresh(existing)

    auth_result = {
        "user_info": {"sub": "provider-user"},
        "provider_user_id": "provider-user",
        "email": "shared@example.com",
        "name": "Updated Name",
        "username": None,
        "phone": None,
        "avatar_url": None,
        "metadata": {"email_verified": True},
    }

    user = await service._find_or_create_oauth_user("oidc", auth_result)

    assert user.id == existing.id
    assert user.email == "shared@example.com"


@pytest.mark.asyncio
async def test_find_or_create_oauth_user_rejects_unverified_existing_email(db_session) -> None:
    service = AuthService(db_session, _jwt_config())
    existing = User(
        email="unverified-local@example.com",
        name="Local Unverified User",
        password_hash="hashed",
        primary_auth_provider="local",
        provider_user_id="unverified-local@example.com",
        is_active=True,
        is_verified=False,
    )
    db_session.add(existing)
    await db_session.commit()

    auth_result = {
        "user_info": {"sub": "attacker-sub"},
        "provider_user_id": "attacker-sub",
        "email": "unverified-local@example.com",
        "name": "Attacker",
        "username": None,
        "phone": None,
        "avatar_url": None,
        "metadata": {"email_verified": True},
    }

    with pytest.raises(ValueError, match="cannot be automatically linked"):
        await service._find_or_create_oauth_user("oidc", auth_result)

"""Security regression tests for glean_core auth, schemas, tokens, and IDOR isolation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from pydantic import ValidationError

from glean_core import arq_json_deserializer, arq_json_serializer, escape_like_pattern
from glean_core.auth import (
    JWTConfig,
    create_admin_refresh_token,
    create_refresh_token,
    hash_password,
    verify_admin_token,
    verify_token,
)
from glean_core.schemas import BookmarkCreate, LoginRequest, RegisterRequest, UserUpdate
from glean_core.schemas.admin import AdminChangePasswordRequest, AdminFeedUpdateRequest
from glean_core.services import APITokenService, BookmarkService, TagService
from glean_database.models import Bookmark, Entry, Feed, Tag, User


def _jwt_cfg() -> JWTConfig:
    return JWTConfig(
        secret_key="test-super-secret-signing-key-32-chars!!",
        algorithm="HS256",
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
    )


class TestArqJsonSerializer:
    """Tests for pickle-free Arq job serialization."""

    def test_round_trip_json(self) -> None:
        payload = {"job": "fetch_feed", "args": ["feed-1", 42], "nested": {"ok": True}}
        raw = arq_json_serializer(payload)
        assert isinstance(raw, bytes)
        assert arq_json_deserializer(raw) == payload

    def test_rejects_pickle_bytes(self) -> None:
        import pickle

        pickled = pickle.dumps({"evil": "payload"})
        with pytest.raises((UnicodeDecodeError, ValueError)):
            arq_json_deserializer(pickled)


class TestJWTAndSchemaSecurity:
    """Tests for strict JWT claims, password bounds, and Pydantic input checks."""

    def test_jwt_rejects_alg_none_and_missing_exp(self) -> None:
        cfg = _jwt_cfg()
        none_alg_token = jwt.encode(
            {"sub": "u1", "type": "access", "exp": 4102444800},
            "",
            algorithm="none",
        )
        assert verify_token(none_alg_token, cfg) is None
        assert verify_admin_token(none_alg_token, cfg) is None

        no_exp = jwt.encode({"sub": "u1", "type": "access"}, cfg.secret_key, algorithm="HS256")
        assert verify_token(no_exp, cfg) is None
        assert verify_admin_token(no_exp, cfg) is None

        expired = jwt.encode(
            {
                "sub": "u1",
                "type": "admin",
                "exp": int((datetime.now(UTC) - timedelta(minutes=5)).timestamp()),
            },
            cfg.secret_key,
            algorithm="HS256",
        )
        assert verify_admin_token(expired, cfg) is None

    def test_refresh_tokens_include_unique_jti(self) -> None:
        cfg = _jwt_cfg()
        t1 = create_refresh_token("user-1", cfg)
        t2 = create_refresh_token("user-1", cfg)
        d1 = verify_token(t1, cfg)
        d2 = verify_token(t2, cfg)
        assert d1 is not None and d1.jti
        assert d2 is not None and d2.jti
        assert d1.jti != d2.jti

        a1 = create_admin_refresh_token("admin-1", cfg)
        a2 = create_admin_refresh_token("admin-1", cfg)
        p1 = verify_admin_token(a1, cfg)
        p2 = verify_admin_token(a2, cfg)
        assert p1 is not None and p2 is not None
        assert p1["jti"] != p2["jti"]

    def test_password_72_byte_bounds(self) -> None:
        over_bytes = "€" * 25  # 25 chars * 3 bytes = 75 UTF-8 bytes
        with pytest.raises(ValidationError):
            RegisterRequest(email="a@example.com", name="A", password=over_bytes)
        with pytest.raises(ValidationError):
            LoginRequest(email="a@example.com", password=over_bytes)
        with pytest.raises(ValidationError):
            AdminChangePasswordRequest(current_password="oldpass123", new_password=over_bytes)
        with pytest.raises(ValueError, match="72 bytes"):
            hash_password(over_bytes)

    def test_url_and_settings_size_validators(self) -> None:
        with pytest.raises(ValidationError):
            BookmarkCreate(url="javascript:alert(1)")
        with pytest.raises(ValidationError):
            UserUpdate(avatar_url="ftp://files.example/pic.png")
        with pytest.raises(ValidationError):
            AdminFeedUpdateRequest(url="file:///etc/passwd")
        with pytest.raises(ValidationError):
            UserUpdate(settings={"blob": "x" * 40000})

    def test_escape_like_pattern_escapes_wildcards_and_backslash(self) -> None:
        assert escape_like_pattern(r"100%_off\now") == r"100\%\_off\\now"


@pytest.mark.asyncio
class TestServiceIsolationAndTokens:
    """Database-backed checks for API token caps/active state and IDOR isolation."""

    async def test_api_token_cap_sha256_and_inactive_user_rejection(self, db_session) -> None:
        user = User(
            id=str(uuid4()),
            email="tokencap@example.com",
            name="Token Cap",
            password_hash="x",
            primary_auth_provider="local",
            provider_user_id="tokencap@example.com",
            is_active=True,
            is_verified=True,
        )
        db_session.add(user)
        await db_session.commit()

        service = APITokenService(db_session)
        last_plain = ""
        for idx in range(20):
            res = await service.create_token(user_id=user.id, name=f"tok-{idx}")
            assert res.token.startswith("glean_")
            last_plain = res.token

        assert await service.verify_token(last_plain) is not None

        with pytest.raises(ValueError, match="Maximum"):
            await service.create_token(user_id=user.id, name="tok-21")

        # Deactivating user invalidates token verification immediately
        user.is_active = False
        await db_session.commit()
        assert await service.verify_token(last_plain) is None

    async def test_bookmark_and_tag_idor_isolation(self, db_session) -> None:
        victim = User(
            id=str(uuid4()),
            email="victim@example.com",
            name="Victim",
            password_hash="x",
            primary_auth_provider="local",
            provider_user_id="victim@example.com",
            is_active=True,
            is_verified=True,
        )
        attacker = User(
            id=str(uuid4()),
            email="attacker@example.com",
            name="Attacker",
            password_hash="x",
            primary_auth_provider="local",
            provider_user_id="attacker@example.com",
            is_active=True,
            is_verified=True,
        )
        feed = Feed(
            id=str(uuid4()),
            url=f"https://example.com/feed-{uuid4().hex}.xml",
            title="Feed",
        )
        db_session.add_all([victim, attacker, feed])
        await db_session.flush()

        private_entry = Entry(
            id=str(uuid4()),
            feed_id=feed.id,
            guid="guid-1",
            url="https://example.com/item-1",
            title="Secret Entry",
        )
        victim_bookmark = Bookmark(
            id=str(uuid4()),
            user_id=victim.id,
            title="Victim Bookmark",
            url="https://example.com/vm",
        )
        attacker_tag = Tag(id=str(uuid4()), user_id=attacker.id, name="attacker-tag")
        db_session.add_all([private_entry, victim_bookmark, attacker_tag])
        await db_session.commit()

        bookmark_service = BookmarkService(db_session)
        # Attacker is not subscribed to feed -> bookmarking entry_id must be rejected
        with pytest.raises(ValueError):
            await bookmark_service.create_bookmark(
                attacker.id, BookmarkCreate(entry_id=private_entry.id)
            )

        # Attacker batch-tagging victim bookmark ID must affect 0 records
        tag_service = TagService(db_session)
        affected = await tag_service.batch_add_tag(
            user_id=attacker.id,
            tag_id=attacker_tag.id,
            target_type="bookmark",
            target_ids=[victim_bookmark.id],
        )
        assert affected == 0

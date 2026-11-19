"""Integration tests for the personal-token browser extension API."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core.services import APITokenService
from glean_database.models import User


@pytest.fixture
async def extension_headers(
    db_session: AsyncSession, test_user: User
) -> tuple[str, dict[str, str]]:
    token = await APITokenService(db_session).create_token(test_user.id, "Browser extension")
    return token.id, {"Authorization": f"Bearer {token.token}"}


@pytest.mark.asyncio
async def test_extension_api_writes_for_token_owner(
    client: AsyncClient,
    auth_headers: dict[str, str],
    extension_headers,
    monkeypatch,
    test_mock_redis,
):
    discovered = AsyncMock(return_value=("https://example.com/feed.xml", "Example Feed"))
    monkeypatch.setattr("glean_api.routers.feeds.discover_feed", discovered)
    token_id, headers = extension_headers

    connection = await client.get("/api/extension/connection", headers=headers)
    assert connection.status_code == 204
    assert connection.headers["Cache-Control"] == "no-store"
    tokens = (await client.get("/api/tokens", headers=auth_headers)).json()["tokens"]
    assert tokens[0]["id"] == token_id
    assert tokens[0]["last_used_at"] is not None

    page_url = "https://example.com/article"
    subscription = await client.post(
        "/api/extension/subscriptions", json={"url": page_url}, headers=headers
    )
    assert subscription.status_code == 201
    discovered.assert_awaited_once_with(page_url)
    duplicate = await client.post(
        "/api/extension/subscriptions", json={"url": page_url}, headers=headers
    )
    assert duplicate.status_code == 409
    subscriptions = await client.get("/api/feeds", headers=auth_headers)
    assert subscriptions.json()["items"][0]["feed"]["url"] == "https://example.com/feed.xml"

    bookmark = await client.post(
        "/api/extension/bookmarks", json={"url": page_url, "title": "An article"}, headers=headers
    )
    assert bookmark.status_code == 201
    bookmarks = await client.get("/api/bookmarks", headers=auth_headers)
    item = bookmarks.json()["items"][0]
    assert (item["url"], item["title"]) == (page_url, "An article")
    assert any(job[0] == "fetch_bookmark_metadata_task" for job in test_mock_redis.enqueued_jobs)

    for path in ("/api/tokens", "/api/bookmarks", "/api/feeds"):
        assert (await client.get(path, headers=headers)).status_code == 401


@pytest.mark.asyncio
async def test_missing_or_invalid_key_and_jwt_are_rejected(client: AsyncClient, auth_headers):
    valid_payload = {"url": "https://example.com/article"}
    for headers in ({}, {"Authorization": "Bearer glean_invalid"}, auth_headers):
        assert (await client.get("/api/extension/connection", headers=headers)).status_code == 401
        for path in ("subscriptions", "bookmarks"):
            response = await client.post(
                f"/api/extension/{path}", json=valid_payload, headers=headers
            )
            assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["revoked", "expired", "inactive"])
async def test_unusable_token_is_rejected(
    client: AsyncClient, db_session: AsyncSession, test_user: User, extension_headers, state: str
):
    token_id, headers = extension_headers
    service = APITokenService(db_session)
    if state == "revoked":
        await service.revoke_token(token_id, test_user.id)
    elif state == "expired":
        token = await service.verify_token(headers["Authorization"].removeprefix("Bearer "))
        assert token is not None
        token.expires_at = datetime.now(UTC) - timedelta(days=1)
        await db_session.commit()
    else:
        test_user.is_active = False
        await db_session.commit()

    assert (await client.get("/api/extension/connection", headers=headers)).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["file:///tmp/article", "https://user:secret@example.com"])
async def test_extension_only_accepts_web_urls_without_credentials(
    client: AsyncClient, extension_headers, url: str
):
    _, headers = extension_headers
    for path in ("subscriptions", "bookmarks"):
        response = await client.post(f"/api/extension/{path}", json={"url": url}, headers=headers)
        assert response.status_code == 422

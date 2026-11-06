"""Admin Jev configuration permissions, key handling and reclassification."""

from unittest.mock import AsyncMock, patch

import pytest

from glean_core.schemas.jev import JevConfig
from glean_core.services import TypedConfigService
from glean_database.models import Entry, Feed, Subscription


async def test_jev_requires_admin(client, auth_headers):
    assert (await client.get("/api/admin/jev/config")).status_code == 401
    for method, path in [
        ("get", "config"),
        ("get", "status"),
        ("put", "config"),
        ("post", "test"),
        ("post", "reclassify"),
    ]:
        response = await getattr(client, method)(f"/api/admin/jev/{path}", headers=auth_headers)
        assert response.status_code in {401, 403}


async def test_saved_key_is_masked_preserved_and_explicitly_cleared(
    client, admin_headers, db_session
):
    path = "/api/admin/jev/config"
    payload = {"enabled": True, "api_key": "test-secret"}
    response = await client.put(path, json=payload, headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["api_key_set"] is True
    assert "test-secret" not in response.text
    assert "api_key" not in response.json()
    response = await client.put(
        path, json={"enabled": True, "ai_prompt": "Custom AI question?"}, headers=admin_headers
    )
    assert response.status_code == 200
    config = await TypedConfigService(db_session).get(JevConfig)
    assert config.api_key == "test-secret"
    assert config.ai_prompt == "Custom AI question?"
    response = await client.put(path, json={"enabled": False, "api_key": ""}, headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["api_key_set"] is False
    assert (await client.get(path, headers=admin_headers)).json()["api_key_set"] is False


async def test_enabling_without_key_and_invalid_categories_are_rejected(client, admin_headers):
    assert (
        await client.put("/api/admin/jev/config", json={"enabled": True}, headers=admin_headers)
    ).status_code == 400
    assert (
        await client.put("/api/admin/jev/config", json={"categories": []}, headers=admin_headers)
    ).status_code == 422


async def test_connection_uses_draft_settings_without_saving(client, admin_headers, db_session):
    service = TypedConfigService(db_session)
    await service.set(JevConfig, JevConfig(api_key="saved-key"))
    with patch("glean_api.routers.admin_jev.test_connection", new_callable=AsyncMock) as test:
        response = await client.post(
            "/api/admin/jev/test",
            json={"base_url": "https://draft.example.com", "api_key": "draft-key"},
            headers=admin_headers,
        )
    assert response.status_code == 200
    candidate = test.call_args.args[0]
    assert candidate.base_url == "https://draft.example.com"
    assert candidate.api_key == "draft-key"
    assert (await service.get(JevConfig)).api_key == "saved-key"
    with patch("glean_api.routers.admin_jev.test_connection", new_callable=AsyncMock) as test:
        await client.post("/api/admin/jev/test", json={}, headers=admin_headers)
    assert test.call_args.args[0].api_key == "saved-key"


@pytest.fixture
async def classified_entry(db_session, test_user):
    feed = Feed(url="https://example.com/jev.xml", title="Jev feed")
    db_session.add(feed)
    await db_session.flush()
    db_session.add(Subscription(user_id=test_user.id, feed_id=feed.id))
    entry = Entry(
        feed_id=feed.id,
        url="https://example.com/article",
        title="Article",
        classification_status="done",
        classification_result={
            "label": "human",
            "score": 0.9,
            "model_id": "jev-test",
            "content": {"label": "original", "name": "Original", "confidence": 0.85},
        },
    )
    db_session.add(entry)
    await db_session.commit()
    return entry


async def test_results_reach_list_detail_and_follow_display_settings(
    client, admin_headers, auth_headers, db_session, classified_entry
):
    service = TypedConfigService(db_session)
    await service.set(JevConfig, JevConfig(enabled=True, api_key="test-key", show_confidence=True))
    response = await client.get("/api/entries", headers=auth_headers)
    assert response.status_code == 200
    result = response.json()["items"][0]["classification"]
    assert result["content"]["name"] == "Original"
    assert result["show_confidence"] is True
    response = await client.get(f"/api/entries/{classified_entry.id}", headers=auth_headers)
    assert response.json()["classification"] == result
    await service.update(JevConfig, classify_content=False, show_confidence=False)
    response = await client.get("/api/entries", headers=auth_headers)
    assert response.json()["items"][0]["classification"]["content"] is None
    assert response.json()["items"][0]["classification"]["show_confidence"] is False
    await service.update(JevConfig, enabled=False)
    response = await client.get("/api/entries", headers=auth_headers)
    assert response.json()["items"][0]["classification"] is None
    assert response.json()["items"][0]["classification_status"] is None


async def test_reclassification_resets_status_and_changes_generation(
    client, admin_headers, db_session, classified_entry
):
    service = TypedConfigService(db_session)
    await service.set(JevConfig, JevConfig(enabled=True, api_key="test-key", version="old"))
    response = await client.get("/api/admin/jev/status", headers=admin_headers)
    assert response.json()["counts"] == {"done": 1}
    response = await client.post("/api/admin/jev/reclassify", headers=admin_headers)
    assert response.status_code == 200
    await db_session.refresh(classified_entry)
    assert classified_entry.classification_status == "pending"
    assert (await service.get(JevConfig)).version != "old"

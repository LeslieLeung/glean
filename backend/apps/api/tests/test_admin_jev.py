"""Admin classification configuration permissions, provider isolation, and reclassification."""

from unittest.mock import AsyncMock, patch

import pytest

from glean_core.schemas.jev import JevConfig
from glean_core.schemas.systemone import ProviderProfile, SystemOneConfig
from glean_core.services import TypedConfigService
from glean_database.models import Entry, Feed, Subscription, SystemConfig


async def test_jev_requires_admin(client, auth_headers):
    for prefix in ("/api/admin/jev", "/api/admin/classification"):
        assert (await client.get(f"{prefix}/config")).status_code == 401
        for method, path in [
            ("get", "config"),
            ("get", "status"),
            ("put", "config"),
            ("post", "test"),
            ("post", "reclassify"),
        ]:
            response = await getattr(client, method)(f"{prefix}/{path}", headers=auth_headers)
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


async def test_per_provider_key_isolation_and_switching(client, admin_headers, db_session):
    base = "/api/admin/classification"
    response = await client.put(
        f"{base}/config",
        json={"enabled": True, "provider": "jev", "api_key": "jev-secret"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["providers"]["jev"]["api_key_set"] is True
    assert response.json()["providers"]["clef"]["api_key_set"] is False
    assert response.json()["providers"]["laya"]["api_key_set"] is False

    # Switching to keyless Laya does not expose or reuse Jev's key.
    with patch(
        "glean_api.routers.admin_classification.test_connection", new_callable=AsyncMock
    ) as test:
        test_res = await client.post(
            f"{base}/test",
            json={"enabled": False, "provider": "laya"},
            headers=admin_headers,
        )
    assert test_res.status_code == 200
    assert test.call_args.args[0].provider == "laya"
    assert test.call_args.args[0].api_key is None

    # Save Clef token, then clear Clef token without touching Jev's saved key.
    account_id = "a" * 32
    response = await client.put(
        f"{base}/config",
        json={
            "enabled": True,
            "provider": "clef",
            "providers": {"clef": {"account_id": account_id, "model": "clef"}},
            "provider_api_keys": {"clef": "cf-secret"},
        },
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "clef"
    assert data["api_key_set"] is True
    assert data["providers"]["jev"]["api_key_set"] is True
    assert data["providers"]["clef"]["api_key_set"] is True
    assert "cf-secret" not in response.text
    assert "jev-secret" not in response.text

    response = await client.put(
        f"{base}/config",
        json={"enabled": False, "provider": "clef", "provider_api_keys": {"clef": ""}},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["providers"]["clef"]["api_key_set"] is False
    assert response.json()["providers"]["jev"]["api_key_set"] is True
    saved = await TypedConfigService(db_session).get(SystemOneConfig)
    assert saved.provider_api_keys == {"jev": "jev-secret"}


async def test_provider_enable_validation_rules(client, admin_headers):
    base = "/api/admin/classification/config"

    # Keyless Laya can be enabled without an API key.
    laya_ok = await client.put(
        base,
        json={
            "enabled": True,
            "provider": "laya",
            "providers": {"laya": {"base_url": "http://localhost:8000", "model": "multilingual"}},
        },
        headers=admin_headers,
    )
    assert laya_ok.status_code == 200
    assert laya_ok.json()["enabled"] is True
    assert laya_ok.json()["provider"] == "laya"

    # Clef rejects missing/invalid account_id or missing token when enabled, allows disabled draft.
    assert (
        await client.put(
            base,
            json={
                "enabled": True,
                "provider": "clef",
                "providers": {"clef": {"account_id": "invalid", "model": "clef-flash"}},
                "api_key": "cf-token",
            },
            headers=admin_headers,
        )
    ).status_code == 400
    assert (
        await client.put(
            base,
            json={
                "enabled": True,
                "provider": "clef",
                "providers": {"clef": {"account_id": "a" * 32, "model": "clef-flash"}},
            },
            headers=admin_headers,
        )
    ).status_code == 400
    assert (
        await client.put(
            base,
            json={"enabled": False, "provider": "clef"},
            headers=admin_headers,
        )
    ).status_code == 200

    # Custom requires both base_url and model when enabled, allows disabled draft.
    assert (
        await client.put(
            base,
            json={
                "enabled": True,
                "provider": "custom",
                "providers": {"custom": {"base_url": "https://sys1.example"}},
            },
            headers=admin_headers,
        )
    ).status_code == 400
    custom_ok = await client.put(
        base,
        json={
            "enabled": True,
            "provider": "custom",
            "providers": {"custom": {"base_url": "https://sys1.example", "model": "my-model"}},
        },
        headers=admin_headers,
    )
    assert custom_ok.status_code == 200
    assert custom_ok.json()["model"] == "my-model"


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
            "show_confidence": False,
            "content": {"label": "original", "name": "Original", "confidence": 0.85},
        },
    )
    db_session.add(entry)
    await db_session.commit()
    return entry


async def test_legacy_config_and_results_keep_both_scores(
    client, admin_headers, auth_headers, db_session, classified_entry
):
    service = TypedConfigService(db_session)
    db_session.add(
        SystemConfig(
            key="jev",
            value={
                "enabled": True,
                "base_url": "https://legacy.typesafe.ai",
                "api_key": "test-key",
                "show_confidence": True,
            },
        )
    )
    await db_session.commit()
    for path in ("/api/admin/jev/config", "/api/admin/classification/config"):
        response = await client.get(path, headers=admin_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["enabled"] is True
        assert body["provider"] == "jev"
        assert body["base_url"] == "https://legacy.typesafe.ai"
        assert body["api_key_set"] is True
        assert "show_confidence" not in body
        assert "show_confidence" not in body["defaults"]
    response = await client.get("/api/entries", headers=auth_headers)
    assert response.status_code == 200
    result = response.json()["items"][0]["classification"]
    assert result["content"]["name"] == "Original"
    assert result["score"] == 0.9
    assert result["content"]["confidence"] == 0.85
    assert result["provider"] is None
    assert "show_confidence" not in result
    response = await client.get(f"/api/entries/{classified_entry.id}", headers=auth_headers)
    assert response.json()["classification"] == result
    await service.update(SystemOneConfig, classify_content=False)
    response = await client.get("/api/entries", headers=auth_headers)
    assert response.json()["items"][0]["classification"]["content"] is None
    await service.update(SystemOneConfig, enabled=False)
    response = await client.get("/api/entries", headers=auth_headers)
    assert response.json()["items"][0]["classification"] is None
    assert response.json()["items"][0]["classification_status"] is None


async def test_reclassification_resets_status_and_changes_generation(
    client, admin_headers, db_session, classified_entry
):
    service = TypedConfigService(db_session)
    await service.set(
        SystemOneConfig,
        SystemOneConfig(
            enabled=True,
            provider="laya",
            providers={
                "laya": ProviderProfile(base_url="http://localhost:8000", model="multilingual")
            },
            version="old",
        ),
    )
    response = await client.get("/api/admin/classification/status", headers=admin_headers)
    assert response.json()["counts"] == {"done": 1}
    response = await client.post("/api/admin/classification/reclassify", headers=admin_headers)
    assert response.status_code == 200
    await db_session.refresh(classified_entry)
    assert classified_entry.classification_status == "pending"
    assert (await service.get(SystemOneConfig)).version != "old"

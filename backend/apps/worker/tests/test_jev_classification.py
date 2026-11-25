"""Worker System One persistence, retry and stale-generation handling."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import httpx
import pytest
from arq import Retry

from glean_core.schemas.jev import EntryClassification, JevConfig
from glean_core.schemas.systemone import ProviderDescriptor, ProviderProfile, SystemOneConfig
from glean_core.services import TypedConfigService
from glean_core.services.systemone_providers import (
    ResolvedConnection,
    SystemOneProvider,
    provider_registry,
    register_provider,
)
from glean_database.models import Entry, Feed
from glean_worker.tasks import jev_classification as worker


@pytest.fixture
async def context(db_session, monkeypatch):
    @asynccontextmanager
    async def session_context():
        yield db_session
        await db_session.commit()

    monkeypatch.setattr(worker, "get_session_context", session_context)
    service = TypedConfigService(db_session)
    await service.set(JevConfig, JevConfig(enabled=True, api_key="test-key", version="one"))
    feed = Feed(url="https://example.com/feed.xml", title="Feed")
    db_session.add(feed)
    await db_session.flush()
    entry = Entry(
        feed_id=feed.id,
        url="https://example.com/article",
        title="Article",
        content="<p>" + "text " * 100 + "</p>",
    )
    db_session.add(entry)
    await db_session.commit()
    classify = AsyncMock(
        return_value=EntryClassification(
            label="human", score=0.9, model_id="jev-test", provider="jev"
        )
    )
    monkeypatch.setattr(worker, "classify_text", classify)
    return entry, service, classify


async def test_classification_is_persisted_and_not_repeated(db_session, context):
    entry, _, classify = context
    assert await worker.classify_entry({}, entry.id) == {"status": "done"}
    await db_session.refresh(entry)
    assert entry.classification_result["label"] == "human"
    assert entry.classification_result["provider"] == "jev"
    assert entry.classified_at is not None
    assert "<p>" not in classify.call_args.args[1]
    assert await worker.classify_entry({}, entry.id) == {"status": "done"}
    assert classify.await_count == 1


async def test_short_article_is_classified_without_skipping(db_session, context):
    entry, _, classify = context
    entry.content = "<p>Short</p>"
    await db_session.commit()
    assert await worker.classify_entry({}, entry.id) == {"status": "done"}
    classify.assert_awaited_once()
    assert classify.call_args.args[1] == "Short"


async def test_disabled_jev_does_not_enqueue_or_classify(context):
    entry, service, classify = context
    await service.update(JevConfig, enabled=False)
    redis = AsyncMock()
    assert await worker.enqueue_jev_classifications({"redis": redis}) == {"queued": 0}
    assert await worker.classify_entry({}, entry.id) == {"status": "disabled"}
    redis.enqueue_job.assert_not_awaited()
    classify.assert_not_awaited()


async def test_pending_existing_articles_are_enqueued_with_stable_ids(context):
    entry, _, _ = context
    redis = AsyncMock()
    assert await worker.enqueue_jev_classifications({"redis": redis}) == {"queued": 1}
    redis.enqueue_job.assert_awaited_once_with(
        "classify_entry", entry.id, _job_id=f"jev:{entry.id}", _expires=600
    )


async def test_network_failures_retry_then_stop_with_sanitized_error(db_session, context):
    entry, _, classify = context
    classify.side_effect = httpx.ReadTimeout("sensitive request diagnostics")
    with pytest.raises(Retry):
        await worker.classify_entry({"job_try": 1}, entry.id)
    assert entry.classification_status == "pending"
    assert await worker.classify_entry({"job_try": 3}, entry.id) == {"status": "failed"}
    await db_session.refresh(entry)
    assert entry.classification_error == "Could not connect to Jev"
    assert entry.classification_result is None


async def test_changed_config_discards_inflight_result(db_session, context):
    entry, service, classify = context

    async def changed_config(*args):
        await service.update(JevConfig, version="two")
        return EntryClassification(label="ai", score=0.8, model_id="jev-test", provider="jev")

    classify.side_effect = changed_config
    assert await worker.classify_entry({}, entry.id) == {"status": "stale"}
    await db_session.refresh(entry)
    assert entry.classification_result is None
    assert entry.classification_status == "pending"


async def test_keyless_laya_enqueues_and_classifies_with_provider_error_name(db_session, context):
    entry, service, classify = context
    await service.set(
        SystemOneConfig,
        SystemOneConfig(
            enabled=True,
            provider="laya",
            providers={
                "laya": ProviderProfile(base_url="http://localhost:8000", model="multilingual")
            },
            version="laya-1",
        ),
    )
    classify.return_value = EntryClassification(
        label="human", score=0.88, model_id="multilingual", provider="laya"
    )
    redis = AsyncMock()
    assert await worker.enqueue_jev_classifications({"redis": redis}) == {"queued": 1}
    assert await worker.classify_entry({}, entry.id) == {"status": "done"}
    await db_session.refresh(entry)
    assert entry.classification_result["provider"] == "laya"
    assert entry.classification_result["model_id"] == "multilingual"

    # Also verify provider-aware sanitized network error for Laya.
    entry.classification_status = "pending"
    await db_session.commit()
    classify.side_effect = httpx.ReadTimeout("sensitive host detail")
    assert await worker.classify_entry({"job_try": 3}, entry.id) == {"status": "failed"}
    await db_session.refresh(entry)
    assert entry.classification_error == "Could not connect to Laya"


async def test_unconfigured_clef_does_not_enqueue_or_classify(context):
    entry, service, classify = context
    await service.set(
        SystemOneConfig,
        SystemOneConfig(
            enabled=True,
            provider="clef",
            providers={"clef": ProviderProfile(account_id=None, model="clef-flash")},
            provider_api_keys={},
            version="clef-1",
        ),
    )
    redis = AsyncMock()
    assert await worker.enqueue_jev_classifications({"redis": redis}) == {"queued": 0}
    assert await worker.classify_entry({}, entry.id) == {"status": "disabled"}
    redis.enqueue_job.assert_not_awaited()
    classify.assert_not_awaited()


async def test_registered_plugin_provider_enqueues_classifies_and_reports_error_name(
    db_session, context, monkeypatch
):
    class CustomAcmeProvider(SystemOneProvider):
        descriptor = ProviderDescriptor(
            id="acme",
            name="Acme Decision",
            default_base_url="https://acme.example",
            default_model="acme-v1",
            requires_api_key=False,
        )

        def inference_url(self, connection: ResolvedConnection) -> str:
            return f"{connection.base_url}/v1/systemone"

    monkeypatch.setattr(provider_registry, "_providers", dict(provider_registry._providers))
    register_provider(CustomAcmeProvider())

    entry, service, classify = context
    await service.set(
        SystemOneConfig,
        SystemOneConfig(enabled=True, provider="acme", version="acme-1"),
    )
    classify.return_value = EntryClassification(
        label="ai", score=0.95, model_id="acme-v1", provider="acme"
    )
    redis = AsyncMock()
    assert await worker.enqueue_jev_classifications({"redis": redis}) == {"queued": 1}
    assert await worker.classify_entry({}, entry.id) == {"status": "done"}
    await db_session.refresh(entry)
    assert entry.classification_result["provider"] == "acme"
    assert entry.classification_result["model_id"] == "acme-v1"

    entry.classification_status = "pending"
    await db_session.commit()
    classify.side_effect = httpx.ReadTimeout("timeout")
    assert await worker.classify_entry({"job_try": 3}, entry.id) == {"status": "failed"}
    await db_session.refresh(entry)
    assert entry.classification_error == "Could not connect to Acme Decision"

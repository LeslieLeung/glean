"""Worker Jev persistence, retry and stale-generation handling."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import httpx
import pytest
from arq import Retry

from glean_core.schemas.jev import EntryClassification, JevConfig
from glean_core.services import TypedConfigService
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
        return_value=EntryClassification(label="human", score=0.9, model_id="jev-test")
    )
    monkeypatch.setattr(worker, "classify_text", classify)
    return entry, service, classify


async def test_classification_is_persisted_and_not_repeated(db_session, context):
    entry, _, classify = context
    assert await worker.classify_entry({}, entry.id) == {"status": "done"}
    await db_session.refresh(entry)
    assert entry.classification_result["label"] == "human"
    assert entry.classified_at is not None
    assert "<p>" not in classify.call_args.args[1]
    assert await worker.classify_entry({}, entry.id) == {"status": "done"}
    assert classify.await_count == 1


async def test_short_article_is_skipped_without_api_call(db_session, context):
    entry, _, classify = context
    entry.content = "<p>Short</p>"
    await db_session.commit()
    assert await worker.classify_entry({}, entry.id) == {"status": "skipped"}
    classify.assert_not_awaited()


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
    assert entry.classification_error == "Could not connect to the Jev server"
    assert entry.classification_result is None


async def test_changed_config_discards_inflight_result(db_session, context):
    entry, service, classify = context

    async def changed_config(*args):
        await service.update(JevConfig, version="two")
        return EntryClassification(label="ai", score=0.8, model_id="jev-test")

    classify.side_effect = changed_config
    assert await worker.classify_entry({}, entry.id) == {"status": "stale"}
    await db_session.refresh(entry)
    assert entry.classification_result is None
    assert entry.classification_status == "pending"

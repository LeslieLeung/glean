"""Integration tests for entry translation API endpoints."""

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def test_entry_for_translation(db_session: AsyncSession, test_subscription, test_feed):
    """Create a test entry with English content for translation."""
    from glean_database.models.entry import Entry

    entry = Entry(
        feed_id=test_feed.id,
        title="Understanding Machine Learning",
        url="https://example.com/ml-article",
        content="<p>Machine learning is a subset of artificial intelligence.</p>",
        published_at=datetime.now(UTC),
    )
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)
    return entry


@pytest_asyncio.fixture
async def test_chinese_entry(db_session: AsyncSession, test_subscription, test_feed):
    """Create a test entry with Chinese content."""
    from glean_database.models.entry import Entry

    entry = Entry(
        feed_id=test_feed.id,
        title="机器学习入门指南",
        url="https://example.com/ml-chinese",
        content="<p>机器学习是人工智能的一个子集，它使计算机能够从数据中学习。</p>",
        published_at=datetime.now(UTC),
    )
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)
    return entry


class TestTranslateEntry:
    """Test POST /entries/{entry_id}/translate endpoint."""

    @pytest.mark.asyncio
    async def test_translate_entry_auto_detect(
        self,
        client: AsyncClient,
        auth_headers,
        test_entry_for_translation,
        test_mock_redis,
    ):
        """Test requesting translation with auto-detect language."""
        entry_id = test_entry_for_translation.id
        response = await client.post(
            f"/api/entries/{entry_id}/translate",
            headers=auth_headers,
            json={"target_language": None},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["entry_id"] == str(entry_id)
        assert data["status"] in ("pending", "processing", "done")
        assert data["target_language"] in ("zh-CN", "en")

    @pytest.mark.asyncio
    async def test_translate_entry_specific_language(
        self,
        client: AsyncClient,
        auth_headers,
        test_entry_for_translation,
        test_mock_redis,
    ):
        """Test requesting translation with a specific target language."""
        entry_id = test_entry_for_translation.id
        response = await client.post(
            f"/api/entries/{entry_id}/translate",
            headers=auth_headers,
            json={"target_language": "zh-CN"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["entry_id"] == str(entry_id)
        assert data["target_language"] == "zh-CN"
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_translate_entry_enqueues_worker_task(
        self,
        client: AsyncClient,
        auth_headers,
        test_entry_for_translation,
        test_mock_redis,
    ):
        """Test that translation request enqueues a worker task."""
        entry_id = test_entry_for_translation.id
        test_mock_redis.enqueued_jobs.clear()

        await client.post(
            f"/api/entries/{entry_id}/translate",
            headers=auth_headers,
            json={"target_language": "zh-CN"},
        )

        assert len(test_mock_redis.enqueued_jobs) == 1
        job_name, _args = test_mock_redis.enqueued_jobs[0]
        assert job_name == "translate_entry_task"

    @pytest.mark.asyncio
    async def test_translate_entry_returns_cached(
        self,
        client: AsyncClient,
        auth_headers,
        test_entry_for_translation,
        db_session: AsyncSession,
    ):
        """Test that cached translation is returned immediately."""
        from glean_database.models.entry_translation import EntryTranslation

        entry_id = test_entry_for_translation.id

        # Create a completed translation record
        translation = EntryTranslation(
            entry_id=str(entry_id),
            target_language="zh-CN",
            translated_title="理解机器学习",
            translated_content="<p>机器学习是人工智能的一个子集。</p>",
            status="done",
        )
        db_session.add(translation)
        await db_session.commit()

        response = await client.post(
            f"/api/entries/{entry_id}/translate",
            headers=auth_headers,
            json={"target_language": "zh-CN"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "done"
        assert data["translated_title"] == "理解机器学习"
        assert data["translated_content"] is not None

    @pytest.mark.asyncio
    async def test_translate_entry_chinese_auto_detects_english(
        self,
        client: AsyncClient,
        auth_headers,
        test_chinese_entry,
    ):
        """Test that Chinese content auto-detects English as target."""
        entry_id = test_chinese_entry.id
        response = await client.post(
            f"/api/entries/{entry_id}/translate",
            headers=auth_headers,
            json={"target_language": None},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["target_language"] == "en"

    @pytest.mark.asyncio
    async def test_translate_nonexistent_entry(self, client: AsyncClient, auth_headers):
        """Test translating a non-existent entry returns 404."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await client.post(
            f"/api/entries/{fake_id}/translate",
            headers=auth_headers,
            json={"target_language": "zh-CN"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_translate_entry_unauthorized(
        self, client: AsyncClient, test_entry_for_translation
    ):
        """Test translation without authentication returns 401."""
        entry_id = test_entry_for_translation.id
        response = await client.post(
            f"/api/entries/{entry_id}/translate",
            json={"target_language": "zh-CN"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_translate_entry_retry_failed(
        self,
        client: AsyncClient,
        auth_headers,
        test_entry_for_translation,
        db_session: AsyncSession,
        test_mock_redis,
    ):
        """Test retrying a failed translation resets the status."""
        from glean_database.models.entry_translation import EntryTranslation

        entry_id = test_entry_for_translation.id

        # Create a failed translation record
        translation = EntryTranslation(
            entry_id=str(entry_id),
            target_language="zh-CN",
            status="failed",
            error="Connection timeout",
        )
        db_session.add(translation)
        await db_session.commit()

        test_mock_redis.enqueued_jobs.clear()

        response = await client.post(
            f"/api/entries/{entry_id}/translate",
            headers=auth_headers,
            json={"target_language": "zh-CN"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "pending"
        assert data["error"] is None


class TestGetTranslation:
    """Test GET /entries/{entry_id}/translation/{target_language} endpoint."""

    @pytest.mark.asyncio
    async def test_get_translation_success(
        self,
        client: AsyncClient,
        auth_headers,
        test_entry_for_translation,
        db_session: AsyncSession,
    ):
        """Test getting an existing translation."""
        from glean_database.models.entry_translation import EntryTranslation

        entry_id = test_entry_for_translation.id

        translation = EntryTranslation(
            entry_id=str(entry_id),
            target_language="zh-CN",
            translated_title="理解机器学习",
            translated_content="<p>机器学习是人工智能的一个子集。</p>",
            status="done",
        )
        db_session.add(translation)
        await db_session.commit()

        response = await client.get(
            f"/api/entries/{entry_id}/translation/zh-CN",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        assert data["entry_id"] == str(entry_id)
        assert data["target_language"] == "zh-CN"
        assert data["translated_title"] == "理解机器学习"
        assert data["status"] == "done"

    @pytest.mark.asyncio
    async def test_get_translation_pending(
        self,
        client: AsyncClient,
        auth_headers,
        test_entry_for_translation,
        db_session: AsyncSession,
    ):
        """Test getting a pending translation returns status."""
        from glean_database.models.entry_translation import EntryTranslation

        entry_id = test_entry_for_translation.id

        translation = EntryTranslation(
            entry_id=str(entry_id),
            target_language="zh-CN",
            status="processing",
        )
        db_session.add(translation)
        await db_session.commit()

        response = await client.get(
            f"/api/entries/{entry_id}/translation/zh-CN",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "processing"
        assert data["translated_title"] is None

    @pytest.mark.asyncio
    async def test_get_translation_not_found(
        self, client: AsyncClient, auth_headers, test_entry_for_translation
    ):
        """Test getting a non-existent translation returns 404."""
        entry_id = test_entry_for_translation.id
        response = await client.get(
            f"/api/entries/{entry_id}/translation/ja",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_translation_unauthorized(
        self, client: AsyncClient, test_entry_for_translation
    ):
        """Test getting translation without authentication returns 401."""
        entry_id = test_entry_for_translation.id
        response = await client.get(
            f"/api/entries/{entry_id}/translation/zh-CN",
        )

        assert response.status_code == 401

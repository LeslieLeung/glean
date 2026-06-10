"""Tests for translation service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from glean_core.services.translation_service import TranslationService, detect_target_language


class TestDetectTargetLanguage:
    """Test detect_target_language function."""

    def test_english_text_returns_chinese(self):
        """English text should translate to Chinese."""
        result = detect_target_language("Machine learning is a branch of AI")
        assert result == "zh-CN"

    def test_chinese_text_returns_english(self):
        """Chinese text should translate to English."""
        result = detect_target_language("机器学习是人工智能的一个重要分支领域")
        assert result == "en"

    def test_empty_text_defaults_to_chinese(self):
        """Empty text should default to Chinese."""
        result = detect_target_language("")
        assert result == "zh-CN"

    def test_mixed_text_mostly_chinese(self):
        """Mixed text with mostly Chinese should translate to English."""
        result = detect_target_language("机器学习 (Machine Learning) 是人工智能的重要分支")
        assert result == "en"

    def test_mixed_text_mostly_english(self):
        """Mixed text with mostly English should translate to Chinese."""
        result = detect_target_language("Machine learning is great, also known as 机器学习")
        assert result == "zh-CN"

    def test_numbers_only_defaults_to_chinese(self):
        """Text with only numbers/symbols defaults to Chinese."""
        result = detect_target_language("12345 67890")
        assert result == "zh-CN"


class TestTranslationServiceRequestTranslation:
    """Test TranslationService.request_translation method."""

    @pytest.mark.asyncio
    async def test_entry_not_found_raises(self):
        """Test that requesting translation for missing entry raises ValueError."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        service = TranslationService(mock_session)

        with pytest.raises(ValueError, match="not found"):
            await service.request_translation("missing-id", "user-1")

    @pytest.mark.asyncio
    async def test_returns_cached_done_translation(self):
        """Test that a completed translation is returned from cache."""
        mock_entry = MagicMock()
        mock_entry.id = "entry-1"
        mock_entry.title = "Hello"
        mock_entry.content = "World"

        mock_translation = MagicMock()
        mock_translation.entry_id = "entry-1"
        mock_translation.target_language = "zh-CN"
        mock_translation.translated_title = "你好"
        mock_translation.translated_content = "世界"
        mock_translation.status = "done"
        mock_translation.error = None

        mock_session = AsyncMock()
        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = mock_entry
        translation_result = MagicMock()
        translation_result.scalar_one_or_none.return_value = mock_translation

        mock_session.execute.side_effect = [entry_result, translation_result]

        service = TranslationService(mock_session)
        result = await service.request_translation("entry-1", "user-1", "zh-CN")

        assert result.status == "done"
        assert result.translated_title == "你好"
        # Should not enqueue a new task
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_pending_translation(self):
        """Test that a pending translation is returned without re-queuing."""
        mock_entry = MagicMock()
        mock_entry.id = "entry-1"
        mock_entry.title = "Hello"
        mock_entry.content = "World"

        mock_translation = MagicMock()
        mock_translation.entry_id = "entry-1"
        mock_translation.target_language = "zh-CN"
        mock_translation.translated_title = None
        mock_translation.translated_content = None
        mock_translation.status = "pending"
        mock_translation.error = None

        mock_session = AsyncMock()
        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = mock_entry
        translation_result = MagicMock()
        translation_result.scalar_one_or_none.return_value = mock_translation

        mock_session.execute.side_effect = [entry_result, translation_result]

        service = TranslationService(mock_session)
        result = await service.request_translation("entry-1", "user-1", "zh-CN")

        assert result.status == "pending"
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_new_translation_and_enqueues(self):
        """Test that a new translation record is created and worker task queued."""
        mock_entry = MagicMock()
        mock_entry.id = "entry-1"
        mock_entry.title = "Hello"
        mock_entry.content = "World"

        mock_session = AsyncMock()
        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = mock_entry

        mock_session.execute.return_value = entry_result

        mock_redis = AsyncMock()
        service = TranslationService(mock_session, mock_redis)

        mock_new_translation = MagicMock()
        mock_new_translation.entry_id = "entry-1"
        mock_new_translation.target_language = "zh-CN"
        mock_new_translation.translated_title = None
        mock_new_translation.translated_content = None
        mock_new_translation.status = "pending"
        mock_new_translation.error = None

        with (
            patch.object(service, "_get_existing", return_value=None),
            patch(
                "glean_core.services.translation_service.EntryTranslation",
                return_value=mock_new_translation,
            ),
        ):
            result = await service.request_translation("entry-1", "user-1", "zh-CN")

        assert result.status == "pending"
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_redis.enqueue_job.assert_called_once_with(
            "translate_entry_task",
            entry_id="entry-1",
            target_language="zh-CN",
            user_id="user-1",
        )

    @pytest.mark.asyncio
    async def test_resets_failed_translation(self):
        """Test that a failed translation is reset and re-queued."""
        mock_entry = MagicMock()
        mock_entry.id = "entry-1"
        mock_entry.title = "Hello"
        mock_entry.content = "World"

        mock_translation = MagicMock()
        mock_translation.entry_id = "entry-1"
        mock_translation.target_language = "zh-CN"
        mock_translation.translated_title = None
        mock_translation.translated_content = None
        mock_translation.status = "failed"
        mock_translation.error = "Previous error"

        mock_session = AsyncMock()
        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = mock_entry
        translation_result = MagicMock()
        translation_result.scalar_one_or_none.return_value = mock_translation

        mock_session.execute.side_effect = [entry_result, translation_result]

        mock_redis = AsyncMock()
        service = TranslationService(mock_session, mock_redis)

        result = await service.request_translation("entry-1", "user-1", "zh-CN")

        assert result.status == "pending"
        assert mock_translation.status == "pending"
        assert mock_translation.error is None
        mock_session.commit.assert_called_once()
        mock_redis.enqueue_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_detect_english_to_chinese(self):
        """Test auto-detection picks Chinese for English content."""
        mock_entry = MagicMock()
        mock_entry.id = "entry-1"
        mock_entry.title = "Machine Learning Guide"
        mock_entry.content = "This is a comprehensive guide to machine learning."

        mock_session = AsyncMock()
        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = mock_entry

        mock_session.execute.return_value = entry_result

        service = TranslationService(mock_session)

        mock_new = MagicMock()
        mock_new.entry_id = "entry-1"
        mock_new.target_language = "zh-CN"
        mock_new.translated_title = None
        mock_new.translated_content = None
        mock_new.status = "pending"
        mock_new.error = None

        with (
            patch.object(service, "_get_existing", return_value=None),
            patch(
                "glean_core.services.translation_service.EntryTranslation",
                return_value=mock_new,
            ),
        ):
            result = await service.request_translation("entry-1", "user-1")

        assert result.target_language == "zh-CN"


class TestTranslationServiceGetTranslation:
    """Test TranslationService.get_translation method."""

    @pytest.mark.asyncio
    async def test_returns_existing_translation(self):
        """Test that existing translation is returned."""
        mock_translation = MagicMock()
        mock_translation.entry_id = "entry-1"
        mock_translation.target_language = "zh-CN"
        mock_translation.translated_title = "标题"
        mock_translation.translated_content = "<p>内容</p>"
        mock_translation.status = "done"
        mock_translation.error = None

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_translation
        mock_session.execute.return_value = mock_result

        service = TranslationService(mock_session)
        result = await service.get_translation("entry-1", "zh-CN")

        assert result is not None
        assert result.status == "done"
        assert result.translated_title == "标题"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        """Test that None is returned when no translation exists."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        service = TranslationService(mock_session)
        result = await service.get_translation("entry-1", "ja")

        assert result is None

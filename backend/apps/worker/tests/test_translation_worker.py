"""Tests for translation worker task."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from glean_worker.tasks.translation import (
    _has_skip_ancestor,
    _translate_html_bilingual,
    _translate_text,
    translate_entry_task,
)


def _make_provider(translate_return="translated", translate_side_effect=None):
    """Create a mock translation provider."""
    provider = MagicMock()
    if translate_side_effect:
        provider.translate.side_effect = translate_side_effect
    else:
        provider.translate.return_value = translate_return
    provider.translate_batch.side_effect = lambda texts, src, tgt: [
        provider.translate(t, src, tgt) for t in texts
    ]
    return provider


class TestTranslateText:
    """Test _translate_text helper function."""

    def test_short_text_translated_directly(self):
        """Test that short text is translated in a single call."""
        provider = _make_provider("你好世界")

        result = _translate_text("Hello world", "auto", "zh-CN", provider)

        assert result == "你好世界"
        provider.translate.assert_called_once_with("Hello world", "auto", "zh-CN")

    def test_empty_text_returns_as_is(self):
        """Test that empty text is returned without translation."""
        provider = _make_provider()

        result = _translate_text("", "auto", "zh-CN", provider)

        assert result == ""
        provider.translate.assert_not_called()

    def test_whitespace_text_returns_as_is(self):
        """Test that whitespace-only text is returned without translation."""
        provider = _make_provider()

        result = _translate_text("   ", "auto", "zh-CN", provider)

        assert result == "   "
        provider.translate.assert_not_called()

    def test_long_text_chunked(self):
        """Test that long text is split into chunks."""
        provider = _make_provider(
            translate_side_effect=lambda t, s, tgt: f"translated({t[:20]}...)"
        )

        # Create text longer than CHUNK_SIZE (4500)
        long_text = ". ".join(["This is a sentence"] * 500)

        result = _translate_text(long_text, "auto", "zh-CN", provider)

        assert result is not None
        assert provider.translate.call_count > 1


class TestHasSkipAncestor:
    """Test _has_skip_ancestor helper function."""

    def test_inside_code(self):
        """Test element inside code is skipped."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup("<code><span>var x</span></code>", "html.parser")
        span = soup.find("span")
        assert _has_skip_ancestor(span) is True

    def test_inside_pre(self):
        """Test element inside pre is skipped."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup("<pre><p>code</p></pre>", "html.parser")
        p = soup.find("p")
        assert _has_skip_ancestor(p) is True

    def test_normal_element(self):
        """Test normal element is not skipped."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup("<div><p>text</p></div>", "html.parser")
        p = soup.find("p")
        assert _has_skip_ancestor(p) is False


class TestTranslateHtmlBilingual:
    """Test _translate_html_bilingual function."""

    def test_inserts_translation_after_paragraph(self):
        """Test that translation is inserted after each paragraph."""
        provider = _make_provider("你好世界")

        html = "<p>Hello world</p>"
        result = _translate_html_bilingual(html, "auto", "zh-CN", provider)

        assert "<p>Hello world</p>" in result
        assert 'class="glean-translation"' in result
        assert "你好世界" in result

    def test_preserves_original_content(self):
        """Test that original content is preserved unchanged."""
        provider = _make_provider("翻译")

        html = "<p>First</p><p>Second</p>"
        result = _translate_html_bilingual(html, "auto", "zh-CN", provider)

        assert "<p>First</p>" in result
        assert "<p>Second</p>" in result

    def test_skips_code_blocks(self):
        """Test that code blocks are not translated."""
        provider = _make_provider("可见文本")

        html = "<p>Visible text</p><pre><code>var x = 1;</code></pre>"
        result = _translate_html_bilingual(html, "auto", "zh-CN", provider)

        # Only the <p> should have a translation, not the code
        assert "可见文本" in result
        assert result.count("glean-translation") == 1

    def test_handles_headings(self):
        """Test that headings get bilingual treatment."""
        provider = _make_provider("翻译")

        html = "<h2>Title</h2><p>Content</p>"
        result = _translate_html_bilingual(html, "auto", "zh-CN", provider)

        assert "<h2>Title</h2>" in result
        assert "glean-translation" in result

    def test_empty_html_returns_as_is(self):
        """Test that HTML with no translatable blocks returns unchanged."""
        provider = _make_provider()

        html = "<div><img src='test.png'/></div>"
        result = _translate_html_bilingual(html, "auto", "zh-CN", provider)

        assert result == html

    def test_handles_list_items(self):
        """Test that list items get bilingual treatment."""
        provider = _make_provider("翻译")

        html = "<ul><li>Item one</li><li>Item two</li></ul>"
        result = _translate_html_bilingual(html, "auto", "zh-CN", provider)

        assert "<li>Item one</li>" in result
        assert "<li>Item two</li>" in result
        assert result.count("glean-translation") == 2


class TestTranslateEntryTask:
    """Test translate_entry_task worker function."""

    @pytest.mark.asyncio
    async def test_translation_record_not_found(self):
        """Test task handles missing translation record."""
        mock_session = AsyncMock()

        # First query: user lookup (returns None)
        # Second query: translation lookup (returns None)
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = None
        translation_result = MagicMock()
        translation_result.scalar_one_or_none.return_value = None
        mock_session.execute.side_effect = [user_result, translation_result]

        with (
            patch("glean_worker.tasks.translation.get_session_context") as mock_ctx,
            patch("glean_worker.tasks.translation.create_translation_provider"),
        ):
            mock_ctx.return_value.__aenter__.return_value = mock_session

            result = await translate_entry_task(
                {}, entry_id="nonexistent-id", target_language="zh-CN", user_id="user-1"
            )

        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_entry_not_found(self):
        """Test task handles missing entry."""
        mock_translation = MagicMock()
        mock_translation.status = "pending"
        mock_translation.entry_id = "test-entry-id"

        mock_session = AsyncMock()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = None
        translation_result = MagicMock()
        translation_result.scalar_one_or_none.return_value = mock_translation
        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = None

        mock_session.execute.side_effect = [user_result, translation_result, entry_result]

        with (
            patch("glean_worker.tasks.translation.get_session_context") as mock_ctx,
            patch("glean_worker.tasks.translation.create_translation_provider"),
        ):
            mock_ctx.return_value.__aenter__.return_value = mock_session

            result = await translate_entry_task(
                {}, entry_id="test-entry-id", target_language="zh-CN", user_id="user-1"
            )

        assert result["status"] == "error"
        assert mock_translation.status == "failed"

    @pytest.mark.asyncio
    async def test_successful_translation(self):
        """Test successful entry translation produces bilingual content."""
        mock_translation = MagicMock()
        mock_translation.status = "pending"
        mock_translation.entry_id = "test-entry-id"

        mock_entry = MagicMock()
        mock_entry.id = "test-entry-id"
        mock_entry.title = "Hello World"
        mock_entry.content = "<p>This is content.</p>"
        mock_entry.summary = None

        mock_session = AsyncMock()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = None
        translation_result = MagicMock()
        translation_result.scalar_one_or_none.return_value = mock_translation
        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = mock_entry

        mock_session.execute.side_effect = [user_result, translation_result, entry_result]

        with (
            patch("glean_worker.tasks.translation.get_session_context") as mock_ctx,
            patch("glean_worker.tasks.translation.create_translation_provider"),
            patch("glean_worker.tasks.translation._translate_text") as mock_translate_text,
            patch(
                "glean_worker.tasks.translation._translate_html_bilingual"
            ) as mock_translate_html,
        ):
            mock_ctx.return_value.__aenter__.return_value = mock_session
            mock_translate_text.return_value = "你好世界"
            mock_translate_html.return_value = (
                '<p>This is content.</p><p class="glean-translation">这是内容。</p>'
            )

            result = await translate_entry_task(
                {}, entry_id="test-entry-id", target_language="zh-CN", user_id="user-1"
            )

        assert result["status"] == "success"
        assert mock_translation.status == "done"
        assert mock_translation.translated_title == "你好世界"
        assert "glean-translation" in mock_translation.translated_content
        assert mock_translation.error is None

    @pytest.mark.asyncio
    async def test_translation_uses_summary_when_no_content(self):
        """Test that summary is used when content is None."""
        mock_translation = MagicMock()
        mock_translation.status = "pending"

        mock_entry = MagicMock()
        mock_entry.id = "test-entry-id"
        mock_entry.title = "Title"
        mock_entry.content = None
        mock_entry.summary = "<p>Summary text.</p>"

        mock_session = AsyncMock()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = None
        translation_result = MagicMock()
        translation_result.scalar_one_or_none.return_value = mock_translation
        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = mock_entry

        mock_session.execute.side_effect = [user_result, translation_result, entry_result]

        with (
            patch("glean_worker.tasks.translation.get_session_context") as mock_ctx,
            patch("glean_worker.tasks.translation.create_translation_provider") as mock_create,
            patch("glean_worker.tasks.translation._translate_text") as mock_translate_text,
            patch(
                "glean_worker.tasks.translation._translate_html_bilingual"
            ) as mock_translate_html,
        ):
            mock_provider = MagicMock()
            mock_create.return_value = mock_provider
            mock_ctx.return_value.__aenter__.return_value = mock_session
            mock_translate_text.return_value = "标题"
            mock_translate_html.return_value = "<p>摘要文本。</p>"

            await translate_entry_task(
                {}, entry_id="test-entry-id", target_language="zh-CN", user_id="user-1"
            )

        mock_translate_html.assert_called_once_with(
            "<p>Summary text.</p>", "auto", "zh-CN", mock_provider
        )

    @pytest.mark.asyncio
    async def test_translation_error_sets_failed_status(self):
        """Test that translation errors set failed status."""
        mock_translation = MagicMock()
        mock_translation.status = "pending"

        mock_entry = MagicMock()
        mock_entry.id = "test-entry-id"
        mock_entry.title = "Title"
        mock_entry.content = "<p>Content</p>"
        mock_entry.summary = None

        mock_session = AsyncMock()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = None
        translation_result = MagicMock()
        translation_result.scalar_one_or_none.return_value = mock_translation
        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = mock_entry

        mock_session.execute.side_effect = [user_result, translation_result, entry_result]

        with (
            patch("glean_worker.tasks.translation.get_session_context") as mock_ctx,
            patch("glean_worker.tasks.translation.create_translation_provider"),
            patch("glean_worker.tasks.translation._translate_text") as mock_translate_text,
        ):
            mock_ctx.return_value.__aenter__.return_value = mock_session
            mock_translate_text.side_effect = Exception("API rate limit exceeded")

            result = await translate_entry_task(
                {}, entry_id="test-entry-id", target_language="zh-CN", user_id="user-1"
            )

        assert result["status"] == "error"
        assert mock_translation.status == "failed"
        assert "rate limit" in mock_translation.error.lower()

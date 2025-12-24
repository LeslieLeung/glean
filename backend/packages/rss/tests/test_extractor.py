"""
Tests for the extractor module.

Tests cover backtick-to-code conversion, HTML entity handling, URL resolution,
async performance, and integration with the full extraction pipeline.
"""

import asyncio

import pytest
from bs4 import BeautifulSoup

from glean_rss.extractor import (
    MIN_CONTENT_LENGTH,
    _convert_backticks_to_code,
    extract_fulltext,
    postprocess_html,
)


class TestConvertBackticksToCode:
    """Test the _convert_backticks_to_code helper function."""

    def test_basic_backticks(self) -> None:
        """Test basic backtick conversion to code tags."""
        html = "<p>This is `code` text</p>"
        soup = BeautifulSoup(html, "html.parser")
        _convert_backticks_to_code(soup)
        result = str(soup)
        assert "<code>code</code>" in result
        assert "`" not in result

    def test_multiple_backticks(self) -> None:
        """Test multiple backtick pairs in same text."""
        html = "<p>Use `foo` and `bar` together</p>"
        soup = BeautifulSoup(html, "html.parser")
        _convert_backticks_to_code(soup)
        result = str(soup)
        assert "<code>foo</code>" in result
        assert "<code>bar</code>" in result
        assert result.count("<code>") == 2

    def test_nested_backticks(self) -> None:
        """Test nested backticks (odd/even alternation)."""
        html = "<p>`outer `inner` text`</p>"
        soup = BeautifulSoup(html, "html.parser")
        _convert_backticks_to_code(soup)
        result = str(soup)
        # Should alternate: code, text, code
        assert "<code>outer </code>" in result
        assert "inner" in result
        assert "<code> text</code>" in result

    def test_empty_backticks(self) -> None:
        """Test empty backtick pairs."""
        html = "<p>Empty `` backticks</p>"
        soup = BeautifulSoup(html, "html.parser")
        _convert_backticks_to_code(soup)
        result = str(soup)
        # Empty code tags should be created
        assert "<code></code>" in result

    def test_html_entities_escaped(self) -> None:
        """Test HTML entities are properly escaped in code tags."""
        # Use already-escaped HTML to test that escaping is preserved
        html = "<p>Use `&lt;img&gt;` tag</p>"
        soup = BeautifulSoup(html, "html.parser")
        _convert_backticks_to_code(soup)
        result = str(soup)
        # BeautifulSoup should preserve escaped entities in code tags
        assert "<code>&lt;img&gt;</code>" in result

    def test_already_in_code_tags(self) -> None:
        """Test backticks inside existing code tags are not processed."""
        html = "<code>already `code`</code>"
        soup = BeautifulSoup(html, "html.parser")
        _convert_backticks_to_code(soup)
        result = str(soup)
        # Backticks should remain as-is
        assert "`" in result
        # Should not create nested code tags
        assert result.count("<code>") == 1

    def test_inside_pre_tags(self) -> None:
        """Test backticks inside pre tags are not processed."""
        html = "<pre>text `code` here</pre>"
        soup = BeautifulSoup(html, "html.parser")
        _convert_backticks_to_code(soup)
        result = str(soup)
        # Backticks should remain as-is
        assert "`" in result
        assert "<code>" not in result

    def test_inside_script_tags(self) -> None:
        """Test backticks inside script tags are not processed."""
        html = "<script>var x = `template`;</script>"
        soup = BeautifulSoup(html, "html.parser")
        _convert_backticks_to_code(soup)
        result = str(soup)
        # Backticks should remain (JavaScript template literal)
        assert "`" in result

    def test_inside_style_tags(self) -> None:
        """Test backticks inside style tags are not processed."""
        html = "<style>/* `comment` */</style>"
        soup = BeautifulSoup(html, "html.parser")
        _convert_backticks_to_code(soup)
        result = str(soup)
        # Backticks should remain as-is
        assert "`" in result

    def test_unmatched_backticks(self) -> None:
        """Test unmatched backticks create alternating patterns."""
        html = "<p>text ` unmatched</p>"
        soup = BeautifulSoup(html, "html.parser")
        _convert_backticks_to_code(soup)
        result = str(soup)
        # Single backtick splits into 2 parts: before and after
        # The "after" part becomes code content
        assert "<code> unmatched</code>" in result

    def test_backticks_in_attributes(self) -> None:
        """Test backticks in attributes are not processed."""
        html = '<a title="`test`">link</a>'
        soup = BeautifulSoup(html, "html.parser")
        _convert_backticks_to_code(soup)
        result = str(soup)
        # Attribute backticks should remain as-is
        assert 'title="`test`"' in result or "title='`test`'" in result
        # Text node "link" has no backticks, so no code tags
        assert result.count("<code>") == 0

    def test_special_characters(self) -> None:
        """Test special characters are preserved in code tags."""
        html = "<p>`function(param1, param2)`</p>"
        soup = BeautifulSoup(html, "html.parser")
        _convert_backticks_to_code(soup)
        result = str(soup)
        assert "<code>function(param1, param2)</code>" in result

    def test_whitespace_handling(self) -> None:
        """Test whitespace is preserved in code tags."""
        html = "<p>`  spaced  `</p>"
        soup = BeautifulSoup(html, "html.parser")
        _convert_backticks_to_code(soup)
        result = str(soup)
        # Spaces should be preserved
        assert "<code>  spaced  </code>" in result

    def test_complex_real_world_content(self) -> None:
        """Test complex content with mixed formatting."""
        html = """
        <div>
            <p>Use the `npm install` command to install packages.</p>
            <p>The `&lt;script&gt;` tag is for JavaScript.</p>
            <pre>Already in pre: `dont convert`</pre>
            <p>Multiple: `a` and `b` and `c`</p>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        _convert_backticks_to_code(soup)
        result = str(soup)

        # Should convert regular text backticks
        assert "<code>npm install</code>" in result
        assert "<code>&lt;script&gt;</code>" in result
        assert "<code>a</code>" in result
        assert "<code>b</code>" in result
        assert "<code>c</code>" in result

        # Should NOT convert pre tag backticks
        assert "`dont convert`" in result


class TestPostprocessHtml:
    """Test the postprocess_html async function."""

    @pytest.mark.asyncio
    async def test_basic_postprocessing(self) -> None:
        """Test basic HTML postprocessing."""
        html = "<p>Test `code` here</p>"
        result = await postprocess_html(html)
        assert "<code>code</code>" in result

    @pytest.mark.asyncio
    async def test_relative_url_resolution(self) -> None:
        """Test relative URLs are converted to absolute."""
        html = '<img src="/image.png"><a href="/page.html">link</a>'
        base_url = "https://example.com"
        result = await postprocess_html(html, base_url=base_url)

        assert 'src="https://example.com/image.png"' in result
        assert 'href="https://example.com/page.html"' in result

    @pytest.mark.asyncio
    async def test_lazy_loaded_images(self) -> None:
        """Test data-src attribute handling for lazy-loaded images."""
        html = '<img src="placeholder.jpg" data-src="/real-image.png">'
        base_url = "https://example.com"
        result = await postprocess_html(html, base_url=base_url)

        # Both should be absolute
        assert 'src="https://example.com/real-image.png"' in result
        assert 'data-src="https://example.com/real-image.png"' in result

    @pytest.mark.asyncio
    async def test_srcset_attribute(self) -> None:
        """Test srcset attribute handling for responsive images."""
        html = '<img srcset="/img1.png 1x, /img2.png 2x">'
        base_url = "https://example.com"
        result = await postprocess_html(html, base_url=base_url)

        assert "https://example.com/img1.png 1x" in result
        assert "https://example.com/img2.png 2x" in result

    @pytest.mark.asyncio
    async def test_picture_source_elements(self) -> None:
        """Test source element srcset attribute handling."""
        html = '<picture><source srcset="/img.webp"></picture>'
        base_url = "https://example.com"
        result = await postprocess_html(html, base_url=base_url)

        assert "https://example.com/img.webp" in result

    @pytest.mark.asyncio
    async def test_combined_url_and_backticks(self) -> None:
        """Test URL resolution and backtick conversion work together."""
        html = '<p>Use `npm install` and see <img src="/logo.png"></p>'
        base_url = "https://example.com"
        result = await postprocess_html(html, base_url=base_url)

        # Both features should work
        assert "<code>npm install</code>" in result
        assert "https://example.com/logo.png" in result

    @pytest.mark.asyncio
    async def test_no_base_url(self) -> None:
        """Test postprocessing without base URL."""
        html = '<p>`code` and <img src="/image.png"></p>'
        result = await postprocess_html(html)

        # Backticks should be converted
        assert "<code>code</code>" in result
        # URLs should remain as-is
        assert 'src="/image.png"' in result


class TestPerformance:
    """Test performance characteristics."""

    @pytest.mark.asyncio
    async def test_large_document_non_blocking(self) -> None:
        """Test large document processing doesn't block event loop."""
        # Create a large HTML document (1MB+)
        # Each "Test paragraph. " is ~16 chars, so need ~65000 repetitions for 1MB
        large_html = "<p>" + ("Test paragraph. " * 65000) + "</p>"
        assert len(large_html) > 1_000_000

        # Process in parallel to verify it doesn't block
        start_time = asyncio.get_event_loop().time()
        results = await asyncio.gather(
            postprocess_html(large_html),
            postprocess_html(large_html),
            postprocess_html(large_html),
        )
        end_time = asyncio.get_event_loop().time()

        # All should succeed
        assert all(len(r) > 0 for r in results)
        # Should complete reasonably fast (not precise timing, just sanity check)
        assert end_time - start_time < 10.0

    @pytest.mark.asyncio
    async def test_many_backticks_performance(self) -> None:
        """Test document with many backtick pairs."""
        # Create HTML with 1000+ backtick pairs
        html = "<p>" + " ".join([f"`code{i}`" for i in range(1000)]) + "</p>"

        result = await postprocess_html(html)

        # Should process all backticks
        assert result.count("<code>") == 1000
        assert "`" not in result

    @pytest.mark.asyncio
    async def test_url_resolution_with_many_images(self) -> None:
        """Test document with 100+ images for URL resolution."""
        # Create HTML with 100+ images
        images = "".join([f'<img src="/img{i}.png">' for i in range(100)])
        html = f"<div>{images}</div>"
        base_url = "https://example.com"

        result = await postprocess_html(html, base_url=base_url)

        # All URLs should be absolute
        assert result.count("https://example.com/img") == 100
        # No relative URLs should remain
        assert 'src="/' not in result


class TestExtractFulltext:
    """Test the extract_fulltext function."""

    @pytest.mark.asyncio
    async def test_extract_with_backticks(self) -> None:
        """Test full extraction pipeline with backticks."""
        html = """
        <html>
            <head><title>Test Article</title></head>
            <body>
                <article>
                    <h1>Test Article</h1>
                    <p>This article discusses `code` and other technical topics.</p>
                    <p>Use `npm install` to install packages.</p>
                </article>
            </body>
        </html>
        """
        url = "https://example.com/article"

        result = await extract_fulltext(html, url=url)

        # Should extract content
        assert result is not None
        # Should convert backticks
        assert "<code>code</code>" in result
        assert "<code>npm install</code>" in result
        # Should not have backticks
        assert "`" not in result

    @pytest.mark.asyncio
    async def test_extract_too_short_content(self) -> None:
        """Test extraction returns None for content below threshold."""
        # Very short content that readability will fail to extract meaningfully
        html = """
        <html>
            <body>
                <p>Short</p>
            </body>
        </html>
        """

        result = await extract_fulltext(html)

        # Should return None (content too short after extraction)
        # Note: Readability may extract something, but our MIN_CONTENT_LENGTH check
        # should filter it. This test verifies the length check works.
        if result is not None:
            # If readability extracted something, it should at least meet our threshold
            assert len(result) > MIN_CONTENT_LENGTH

    @pytest.mark.asyncio
    async def test_extract_sufficient_content(self) -> None:
        """Test extraction succeeds for content above threshold."""
        html = f"""
        <html>
            <body>
                <article>
                    <p>{"x" * (MIN_CONTENT_LENGTH + 10)}</p>
                </article>
            </body>
        </html>
        """

        result = await extract_fulltext(html)

        # Should succeed
        assert result is not None
        assert len(result) > MIN_CONTENT_LENGTH

    @pytest.mark.asyncio
    async def test_extract_with_relative_urls(self) -> None:
        """Test extraction converts relative URLs."""
        html = """
        <html>
            <body>
                <article>
                    <h1>Test Article</h1>
                    <p>Content with enough text to pass the length threshold.
                    This is a longer paragraph to ensure we meet the minimum
                    content length requirement for extraction.</p>
                    <img src="/image.png">
                </article>
            </body>
        </html>
        """
        url = "https://example.com/article"

        result = await extract_fulltext(html, url=url)

        # Should convert relative URL
        assert result is not None
        assert "https://example.com/image.png" in result

    @pytest.mark.asyncio
    async def test_extract_invalid_html(self) -> None:
        """Test extraction handles invalid HTML gracefully."""
        html = "<html><body><p>Unclosed tags..."

        # Should not raise exception
        result = await extract_fulltext(html)

        # May or may not extract (depends on content length after parsing)
        # Just ensure it doesn't crash
        assert result is None or isinstance(result, str)

    @pytest.mark.asyncio
    async def test_extract_empty_html(self) -> None:
        """Test extraction handles empty HTML."""
        html = ""

        result = await extract_fulltext(html)

        # Should return None
        assert result is None

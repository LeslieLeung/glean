"""Tests for RSS parser."""

from glean_rss.parser import _get_favicon_url


class TestFaviconURL:
    """Test favicon URL generation."""

    def test_get_favicon_url_valid_http(self) -> None:
        """Test favicon URL generation with valid HTTP URL."""
        url = "http://example.com/blog"
        result = _get_favicon_url(url)
        assert result == "https://www.google.com/s2/favicons?domain=example.com&sz=64"

    def test_get_favicon_url_valid_https(self) -> None:
        """Test favicon URL generation with valid HTTPS URL."""
        url = "https://example.com/blog"
        result = _get_favicon_url(url)
        assert result == "https://www.google.com/s2/favicons?domain=example.com&sz=64"

    def test_get_favicon_url_with_subdomain(self) -> None:
        """Test favicon URL generation with subdomain."""
        url = "https://blog.example.com"
        result = _get_favicon_url(url)
        assert result == "https://www.google.com/s2/favicons?domain=blog.example.com&sz=64"

    def test_get_favicon_url_with_port(self) -> None:
        """Test favicon URL generation with port."""
        url = "http://example.com:8080/blog"
        result = _get_favicon_url(url)
        assert result == "https://www.google.com/s2/favicons?domain=example.com:8080&sz=64"

    def test_get_favicon_url_none(self) -> None:
        """Test favicon URL generation with None."""
        result = _get_favicon_url(None)
        assert result is None

    def test_get_favicon_url_empty(self) -> None:
        """Test favicon URL generation with empty string."""
        result = _get_favicon_url("")
        assert result is None

    def test_get_favicon_url_invalid(self) -> None:
        """Test favicon URL generation with invalid URL."""
        result = _get_favicon_url("not-a-url")
        assert result is None

    def test_get_favicon_url_relative(self) -> None:
        """Test favicon URL generation with relative URL."""
        result = _get_favicon_url("/blog/feed")
        assert result is None


class TestFeedValidation:
    async def test_rejects_non_feed_xml_and_html(self):
        import pytest

        from glean_rss import parse_feed

        for content in ("<html><head><title>Website</title></head></html>", "<document/>", "hello"):
            with pytest.raises(ValueError):
                await parse_feed(content, "https://example.com/feed")

    async def test_accepts_empty_rss_and_atom(self):
        from glean_rss import parse_feed

        for content in (
            '<rss version="2.0"><channel><title>Empty RSS</title><link>https://example.com</link><description>Feed</description></channel></rss>',
            '<feed xmlns="http://www.w3.org/2005/Atom"><title>Empty Atom</title><id>https://example.com</id><updated>2026-01-01T00:00:00Z</updated></feed>',
        ):
            feed = await parse_feed(content, "https://example.com/feed")
            assert feed.title.startswith("Empty")
            assert feed.entries == []

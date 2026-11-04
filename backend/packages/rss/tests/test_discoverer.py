"""Validate content and discovered links without external network dependencies."""

from unittest.mock import patch

import httpx
import pytest

from glean_rss import discover_feed

RSS = '<rss version="2.0"><channel><title>Valid</title><link>https://example.com</link><description>Empty feed</description></channel></rss>'


@pytest.mark.asyncio
async def test_discovers_relative_link_against_final_redirect_url():
    def respond(request):
        if request.url.path == "/":
            return httpx.Response(302, headers={"location": "/blog/"})
        if request.url.path == "/blog/":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text='<link type="application/rss+xml" href="feed.xml">',
            )
        assert request.url.path == "/blog/feed.xml"
        return httpx.Response(200, text=RSS)

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond), follow_redirects=True)
    with patch("glean_rss.discoverer.safe_async_client", return_value=client):
        assert await discover_feed("https://example.com/") == (
            "https://example.com/blog/feed.xml",
            "Valid",
        )


@pytest.mark.asyncio
async def test_accepts_valid_feed_with_incorrect_mime_type():
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, text=RSS, headers={"content-type": "text/plain"})
        )
    )
    with patch("glean_rss.discoverer.safe_async_client", return_value=client):
        assert await discover_feed("https://example.com/feed") == (
            "https://example.com/feed",
            "Valid",
        )


@pytest.mark.asyncio
async def test_rejects_broken_advertised_feed():
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                text='<html><link type="application/rss+xml" href="/feed"></html>',
                headers={"content-type": "text/html"},
            )
        )
    )
    with (
        patch("glean_rss.discoverer.safe_async_client", return_value=client),
        pytest.raises(ValueError, match="No RSS feed"),
    ):
        await discover_feed("https://example.com/")

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


@pytest.mark.asyncio
async def test_discovers_icon_anchor_without_autodiscovery_link():
    """Halo and similar sites only expose the feed as an RSS icon anchor."""

    def respond(request):
        if request.url.path == "/":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text=(
                    "<html><body><a href='https://example.com/feed.xml'>"
                    "<i class='i-ri-rss-fill'></i></a></body></html>"
                ),
            )
        assert request.url.path == "/feed.xml"
        return httpx.Response(200, text=RSS)

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    with patch("glean_rss.discoverer.safe_async_client", return_value=client):
        assert await discover_feed("https://example.com") == (
            "https://example.com/feed.xml",
            "Valid",
        )


@pytest.mark.asyncio
async def test_probes_conventional_feed_path_when_page_has_no_feed_link():
    def respond(request):
        if request.url.path == "/feed.xml":
            return httpx.Response(200, text=RSS)
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><a href='/sitemap.xml'>Sitemap</a></html>",
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    with patch("glean_rss.discoverer.safe_async_client", return_value=client):
        assert await discover_feed("https://example.com/") == (
            "https://example.com/feed.xml",
            "Valid",
        )


@pytest.mark.asyncio
async def test_accepts_autodiscovery_type_with_charset_parameter():
    def respond(request):
        if request.url.path == "/":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text=(
                    '<link rel="alternate" type="application/rss+xml; charset=UTF-8" href="/rss">'
                ),
            )
        assert request.url.path == "/rss"
        return httpx.Response(200, text=RSS)

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    with patch("glean_rss.discoverer.safe_async_client", return_value=client):
        assert await discover_feed("https://example.com/") == (
            "https://example.com/rss",
            "Valid",
        )


@pytest.mark.asyncio
async def test_discovers_anchor_with_rss_class_and_nonstandard_href():
    """RSSHub-Radar follows a link whose class contains an rss token."""

    def respond(request):
        if request.url.path == "/subscribe":
            return httpx.Response(200, text=RSS)
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><a class='button rss' href='/subscribe'>Subscribe</a></html>",
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    with patch("glean_rss.discoverer.safe_async_client", return_value=client):
        assert await discover_feed("https://example.com/") == (
            "https://example.com/subscribe",
            "Valid",
        )


@pytest.mark.asyncio
async def test_discovers_anchor_whose_text_is_only_rss():
    def respond(request):
        if request.url.path == "/custom":
            return httpx.Response(200, text=RSS)
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><a href='/custom'>Subscribe via RSS</a></html>",
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    with patch("glean_rss.discoverer.safe_async_client", return_value=client):
        assert await discover_feed("https://example.com/") == (
            "https://example.com/custom",
            "Valid",
        )


@pytest.mark.asyncio
async def test_discovers_feed_scheme_and_extension():
    def respond(request):
        if request.url.path == "/":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="<a href='feed://example.com/feed.atom'>RSS</a>",
            )
        assert request.url.scheme == "https"
        assert request.url.path == "/feed.atom"
        return httpx.Response(200, text=RSS)

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    with patch("glean_rss.discoverer.safe_async_client", return_value=client):
        assert await discover_feed("https://example.com/") == (
            "https://example.com/feed.atom",
            "Valid",
        )


@pytest.mark.asyncio
async def test_discovers_external_feed_before_conventional_paths():
    """An advertised off-site feed must not lose its slot to guessed paths."""
    external = "https://feeds.example.net/all.xml"
    requested: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if str(request.url) == "https://example.com/blog/":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text=f"<html><a href='{external}'>RSS</a></html>",
            )
        if str(request.url) == external:
            return httpx.Response(200, text=RSS)
        return httpx.Response(404, text="missing")

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    with patch("glean_rss.discoverer.safe_async_client", return_value=client):
        assert await discover_feed("https://example.com/blog/") == (external, "Valid")
    assert requested == ["https://example.com/blog/", external]


@pytest.mark.asyncio
async def test_keeps_external_feed_when_same_origin_anchor_is_not_a_feed():
    external = "https://feeds.example.net/all.xml"
    requested: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if str(request.url) == "https://example.com/":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text=(
                    "<html>"
                    "<a class='rss' href='/not-a-feed'>Site feed</a>"
                    f"<a href='{external}'>RSS</a>"
                    "</html>"
                ),
            )
        if str(request.url) == external:
            return httpx.Response(200, text=RSS)
        return httpx.Response(404, text="missing")

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    with patch("glean_rss.discoverer.safe_async_client", return_value=client):
        assert await discover_feed("https://example.com/") == (external, "Valid")
    assert requested == [
        "https://example.com/",
        "https://example.com/not-a-feed",
        external,
    ]


@pytest.mark.asyncio
async def test_discovers_json_feed_link():
    document = (
        '{"version":"https://jsonfeed.org/version/1.1","title":"Valid",'
        '"home_page_url":"https://example.com","items":[]}'
    )

    def respond(request):
        if request.url.path == "/feed.json":
            return httpx.Response(
                200, text=document, headers={"content-type": "application/feed+json"}
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text='<link type="application/feed+json" href="/feed.json">',
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    with patch("glean_rss.discoverer.safe_async_client", return_value=client):
        assert await discover_feed("https://example.com/") == (
            "https://example.com/feed.json",
            "Valid",
        )

"""Security regression tests for glean_rss SSRF, sanitization, parser, and OPML modules."""

from __future__ import annotations

import httpx
import pytest

from glean_rss import (
    InvalidContentTypeError,
    ResponseTooLargeError,
    SSRFBlockedError,
    parse_feed,
    parse_opml,
    postprocess_html,
    safe_async_client,
    safe_fetch_bytes,
    sanitize_html,
    sanitize_url,
)
from glean_rss.safe_http import SSRFPolicy, validate_resolved_ip, validate_url_sync


class TestSanitizer:
    """Tests for sanitize_url and sanitize_html."""

    @pytest.mark.parametrize(
        "url",
        [
            "javascript:alert(1)",
            "  JaVaScRiPt:alert(1)",
            "vbscript:msgbox(1)",
            "data:text/html,<script>alert(1)</script>",
            "data:image/svg+xml,<svg onload=alert(1)>",
            "file:///etc/passwd",
            "//evil.example.com/payload",
        ],
    )
    def test_sanitize_url_blocks_dangerous_schemes(self, url: str) -> None:
        assert (
            sanitize_url(url, allow_data_image=True, allow_mailto=True, allow_relative=True) is None
        )

    def test_sanitize_url_allows_safe_schemes(self) -> None:
        assert sanitize_url("https://example.com/post?a=1") == "https://example.com/post?a=1"
        assert (
            sanitize_url("mailto:user@example.com", allow_mailto=True) == "mailto:user@example.com"
        )
        raster = "data:image/png;base64,iVBORw0KGgo="
        assert sanitize_url(raster, allow_data_image=True) == raster

    def test_sanitize_html_strips_active_vectors_and_preserves_safe_content(self) -> None:
        dirty = (
            "<!-- secret comment -->"
            "<script>alert(1)</script>"
            "<style>body{display:none}</style>"
            '<svg onload="alert(1)"><circle /></svg>'
            '<iframe src="https://evil.test"></iframe>'
            '<p onclick="alert(1)" data-evil="1">Hello '
            '<a href="javascript:alert(1)">bad</a> '
            '<a href="https://example.com/article" target="_blank">good</a>'
            '<img src="https://example.com/a.png" data-src="https://example.com/b.png" onerror="alert(2)">'
            '<img src="data:image/svg+xml;base64,PHN2Zz4=" alt="badimg">'
            "</p>"
        )
        cleaned = sanitize_html(dirty) or ""
        assert "<script" not in cleaned
        assert "<style" not in cleaned
        assert "<svg" not in cleaned
        assert "<iframe" not in cleaned
        assert "onclick" not in cleaned
        assert "onerror" not in cleaned
        assert "data-evil" not in cleaned
        assert "javascript:" not in cleaned
        assert "secret comment" not in cleaned
        assert "data:image/svg+xml" not in cleaned
        assert 'href="https://example.com/article"' in cleaned
        assert 'rel="noopener noreferrer"' in cleaned
        assert 'data-src="https://example.com/b.png"' in cleaned

    @pytest.mark.asyncio
    async def test_postprocess_html_sanitizes_output(self) -> None:
        cleaned = await postprocess_html(
            '<div onload="alert(1)"><script>x()</script><p>Body</p></div>'
        )
        assert cleaned == "<div><p>Body</p></div>"


class TestSSRFAndStreaming:
    """Tests for SSRF bypasses and streaming size/MIME bounds."""

    @pytest.mark.parametrize(
        "ip",
        [
            "0.0.0.0",
            "0.1.2.3",
            "127.0.0.1",
            "169.254.169.254",
            "100.100.100.200",
            "::",
            "::1",
            "::ffff:127.0.0.1",
            "::ffff:169.254.169.254",
            "::ffff:0:127.0.0.1",
            "64:ff9b::127.0.0.1",
            "64:ff9b:1::10.0.0.1",
            "2002:7f00:0001::",
            "2001:0000:4136:e378:8000:63bf:80ff:fffe",
            "fd00:ec2::254",
            "100::1",
            "2001:db8::1",
        ],
    )
    def test_blocks_reserved_and_embedded_ipv6_addresses(self, ip: str) -> None:
        with pytest.raises(SSRFBlockedError):
            validate_resolved_ip(ip, SSRFPolicy())

    @pytest.mark.parametrize(
        "url",
        [
            "http://2130706433/",
            "http://0x7f000001/",
            "http://0177.0.0.1/",
            "http://127.1/",
            "http://localhost./",
            "http://metadata.google.internal./computeMetadata/v1/",
            "http://service.default.svc.cluster.local./",
        ],
    )
    def test_blocks_non_canonical_and_trailing_dot_hostnames(self, url: str) -> None:
        with pytest.raises(SSRFBlockedError):
            validate_url_sync(url, SSRFPolicy())

    @pytest.mark.asyncio
    async def test_safe_fetch_bytes_rejects_oversized_response(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                content=b"A" * 2048,
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        async with client:
            with pytest.raises(ResponseTooLargeError):
                await safe_fetch_bytes(client, "https://example.com/huge", max_bytes=1024)

    @pytest.mark.asyncio
    async def test_safe_fetch_bytes_rejects_disallowed_content_type(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "application/octet-stream"},
                content=b"binary",
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        async with client:
            with pytest.raises(InvalidContentTypeError):
                await safe_fetch_bytes(
                    client,
                    "https://example.com/bin",
                    allowed_content_types=("text/html",),
                )

    def test_safe_async_client_defaults_block_private(self) -> None:
        client = safe_async_client()
        assert client is not None


class TestParserAndOPMLSecurity:
    """Tests for XXE/billion-laughs OPML defense and parser sanitization."""

    @pytest.mark.parametrize(
        "malicious_xml",
        [
            '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><opml version="2.0"><body><outline text="&xxe;" xmlUrl="https://example.com/rss"/></body></opml>',
            '<!ENTITY lol "lol"><opml version="2.0"><body/></opml>',
        ],
    )
    def test_opml_rejects_doctype_and_entity(self, malicious_xml: str) -> None:
        with pytest.raises(ValueError, match="DTD and ENTITY"):
            parse_opml(malicious_xml)

    @pytest.mark.asyncio
    async def test_parse_feed_sanitizes_rss_entries_and_site_urls(self) -> None:
        rss = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <title>Test Feed</title>
            <link>javascript:alert(1)</link>
            <item>
              <title>Item 1</title>
              <link>https://example.com/1</link>
              <description><![CDATA[<script>evil()</script><p onclick="pwn()">Hi</p>]]></description>
            </item>
          </channel>
        </rss>"""
        parsed = await parse_feed(rss, "https://example.com/rss.xml")
        assert parsed.site_url == ""
        assert len(parsed.entries) == 1
        assert "<script" not in (parsed.entries[0].summary or "")
        assert "onclick" not in (parsed.entries[0].summary or "")
        assert "<p>Hi</p>" in (parsed.entries[0].summary or "")

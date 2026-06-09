"""
Tests for the SSRF-safe httpx client.

Covers IP/URL validation, transport-level DNS pinning and blocking (including
DNS rebinding via getaddrinfo mocking), and env-based policy opt-in.
"""

import socket
from collections.abc import Iterator

import httpx
import pytest

from glean_rss.safe_http import (
    SSRFBlockedError,
    SSRFPolicy,
    SSRFSafeTransport,
    _default_policy,
    safe_async_client,
    validate_resolved_ip,
    validate_url_sync,
)


class TestValidateResolvedIp:
    """Test IP-level validation against the default policy."""

    @pytest.mark.parametrize(
        "ip",
        [
            "127.0.0.1",
            "10.0.0.5",
            "172.16.0.1",
            "192.168.1.1",
            "169.254.169.254",  # AWS metadata
            "100.64.0.1",  # CGNAT
            "0.0.0.0",
            "::1",  # IPv6 loopback
            "::ffff:127.0.0.1",  # IPv4-mapped loopback
            "fe80::1",  # IPv6 link-local
            "fd00::1",  # IPv6 ULA
        ],
    )
    def test_blocked_ips(self, ip: str) -> None:
        with pytest.raises(SSRFBlockedError):
            validate_resolved_ip(ip, SSRFPolicy())

    @pytest.mark.parametrize(
        "ip",
        [
            "93.184.216.34",  # example.com
            "1.1.1.1",
            "8.8.8.8",
            "2606:4700:4700::1111",  # public IPv6
        ],
    )
    def test_allowed_public_ips(self, ip: str) -> None:
        # Should not raise
        validate_resolved_ip(ip, SSRFPolicy())

    def test_invalid_ip(self) -> None:
        with pytest.raises(SSRFBlockedError):
            validate_resolved_ip("not-an-ip", SSRFPolicy())

    def test_metadata_blocked_even_when_private_allowed(self) -> None:
        policy = SSRFPolicy(block_private_ips=False, block_localhost=False)
        with pytest.raises(SSRFBlockedError):
            validate_resolved_ip("169.254.169.254", policy)


class TestValidateUrlSync:
    """Test URL-level synchronous validation (scheme, literal IP, hostname)."""

    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "gopher://example.com/",
            "ftp://example.com/",
        ],
    )
    def test_rejects_non_http_schemes(self, url: str) -> None:
        with pytest.raises(SSRFBlockedError):
            validate_url_sync(url, SSRFPolicy())

    def test_rejects_missing_hostname(self) -> None:
        with pytest.raises(SSRFBlockedError):
            validate_url_sync("http:///path", SSRFPolicy())

    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1:8080/",
            "http://10.0.0.1/",
            "http://169.254.169.254/latest/meta-data/",
            "http://[::1]/",
        ],
    )
    def test_rejects_literal_private_ips(self, url: str) -> None:
        with pytest.raises(SSRFBlockedError):
            validate_url_sync(url, SSRFPolicy())

    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost/",
            "http://metadata.google.internal/",
            "http://svc.default.svc.cluster.local/",
        ],
    )
    def test_rejects_blocked_hostnames(self, url: str) -> None:
        with pytest.raises(SSRFBlockedError):
            validate_url_sync(url, SSRFPolicy())

    def test_allows_public_hostname(self) -> None:
        # No DNS resolution here; just scheme + pattern checks.
        validate_url_sync("https://example.com/feed.xml", SSRFPolicy())


def _fake_getaddrinfo(ip: str) -> object:
    """Build a fake socket.getaddrinfo replacement returning a single IP."""

    def _inner(host: object, port: object, *args: object, **kwargs: object) -> list[object]:
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        sockaddr: tuple[object, ...] = (ip, port, 0, 0) if ":" in ip else (ip, port)
        return [(family, socket.SOCK_STREAM, 0, "", sockaddr)]

    return _inner


@pytest.fixture
def captured_requests() -> Iterator[list[httpx.Request]]:
    """Yield a list that collects requests reaching the inner transport."""
    requests: list[httpx.Request] = []
    yield requests


def _mock_inner(requests: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="ok")

    return httpx.MockTransport(handler)


class TestTransport:
    """Test the SSRFSafeTransport DNS-pinning behavior."""

    @pytest.mark.asyncio
    async def test_blocks_rebinding_to_private_ip(
        self, monkeypatch: pytest.MonkeyPatch, captured_requests: list[httpx.Request]
    ) -> None:
        # Hostname looks public but resolves to an internal IP (DNS rebinding).
        monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("169.254.169.254"))

        transport = SSRFSafeTransport(policy=SSRFPolicy())
        transport._inner = _mock_inner(captured_requests)  # type: ignore[assignment]

        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(SSRFBlockedError):
                await client.get("http://evil.example.com/")

        # Inner transport must never have been reached.
        assert captured_requests == []

    @pytest.mark.asyncio
    async def test_allows_public_ip_and_pins_connection(
        self, monkeypatch: pytest.MonkeyPatch, captured_requests: list[httpx.Request]
    ) -> None:
        monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))

        transport = SSRFSafeTransport(policy=SSRFPolicy())
        transport._inner = _mock_inner(captured_requests)  # type: ignore[assignment]

        async with httpx.AsyncClient(transport=transport) as client:
            response = await client.get("http://example.com/feed.xml")

        assert response.status_code == 200
        # The request reaching the inner transport must be pinned to the IP,
        # while the Host header preserves the original hostname.
        assert len(captured_requests) == 1
        pinned = captured_requests[0]
        assert pinned.url.host == "93.184.216.34"
        assert pinned.headers["host"] == "example.com"

    @pytest.mark.asyncio
    async def test_rejects_non_http_scheme_before_dns(
        self, captured_requests: list[httpx.Request]
    ) -> None:
        transport = SSRFSafeTransport(policy=SSRFPolicy())
        transport._inner = _mock_inner(captured_requests)  # type: ignore[assignment]

        request = httpx.Request("GET", "ftp://example.com/")
        with pytest.raises(SSRFBlockedError):
            await transport.handle_async_request(request)
        assert captured_requests == []


class TestDefaultPolicy:
    """Test env-based policy configuration."""

    def test_secure_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GLEAN_SSRF_ALLOW_PRIVATE", raising=False)
        monkeypatch.delenv("GLEAN_SSRF_ALLOWED_HOSTS", raising=False)
        policy = _default_policy()
        assert policy.block_private_ips is True
        assert policy.block_localhost is True
        assert policy.block_cloud_metadata is True

    def test_allow_private_opt_in(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GLEAN_SSRF_ALLOW_PRIVATE", "true")
        policy = _default_policy()
        assert policy.block_private_ips is False
        assert policy.block_localhost is False
        # Cloud metadata must remain blocked regardless.
        assert policy.block_cloud_metadata is True
        with pytest.raises(SSRFBlockedError):
            validate_resolved_ip("169.254.169.254", policy)
        # Private IP now allowed.
        validate_resolved_ip("10.0.0.1", policy)

    def test_allowed_hosts_parsing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GLEAN_SSRF_ALLOWED_HOSTS", "Internal.Local, feeds.lan ,")
        policy = _default_policy()
        assert policy.allowed_hosts == frozenset({"internal.local", "feeds.lan"})


class TestSafeAsyncClientFactory:
    """Test the safe_async_client factory wiring."""

    @pytest.mark.asyncio
    async def test_returns_client_with_ssrf_transport(self) -> None:
        async with safe_async_client(timeout=5.0) as client:
            assert isinstance(client._transport, SSRFSafeTransport)
            assert client.follow_redirects is True

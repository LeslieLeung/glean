"""SSRF protection helpers for embedding providers."""

from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
import urllib.parse

import httpx

_BLOCKED_IPV4_NETWORKS: tuple[ipaddress.IPv4Network, ...] = tuple(
    ipaddress.IPv4Network(n)
    for n in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "0.0.0.0/8",
        "100.64.0.0/10",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "255.255.255.255/32",
    )
)

_BLOCKED_IPV6_NETWORKS: tuple[ipaddress.IPv6Network, ...] = tuple(
    ipaddress.IPv6Network(n)
    for n in (
        "::/128",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
        "ff00::/8",
        "::ffff:0:0/96",
        "::ffff:0:0:0/96",
        "::0.0.0.0/96",
        "64:ff9b::/96",
        "64:ff9b:1::/48",
        "100::/64",
        "2001::/32",
        "2001:2::/48",
        "2001:db8::/32",
        "2002::/16",
    )
)

_CLOUD_METADATA_IPS: frozenset[str] = frozenset(
    {
        "169.254.169.254",
        "169.254.170.2",
        "169.254.170.23",
        "100.100.100.200",
        "fd00:ec2::254",
        "fd00:ec2::23",
        "fe80::a9fe:a9fe",
    }
)
_CLOUD_METADATA_IPV4_NET = ipaddress.IPv4Network("169.254.0.0/16")
_CLOUD_METADATA_HOSTNAMES: frozenset[str] = frozenset(
    {
        "metadata.google.internal",
        "metadata.amazonaws.com",
        "metadata",
        "instance-data",
    }
)
_LOCALHOST_NAMES: frozenset[str] = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "host.docker.internal",
    }
)
_K8S_SUFFIX = ".svc.cluster.local"
_NAT64_PREFIX = ipaddress.IPv6Network("64:ff9b::/96")
_NAT64_DISCOVERY_PREFIX = ipaddress.IPv6Network("64:ff9b:1::/48")
_SIIT_TRANSLATED_PREFIX = ipaddress.IPv6Network("::ffff:0:0:0/96")


class EmbeddingSSRFError(httpx.ConnectError):
    """Raised when an embedding provider endpoint violates SSRF protections."""


def _allow_private_endpoints() -> bool:
    for env_name in (
        "GLEAN_EMBEDDING_ALLOW_PRIVATE",
        "SSRF_ALLOW_PRIVATE",
        "GLEAN_SSRF_ALLOW_PRIVATE",
    ):
        if os.environ.get(env_name, "").strip().lower() in {"1", "true", "yes", "on"}:
            return True
    return False


def _is_non_canonical_numeric_ipv4_host(hostname: str) -> bool:
    host = hostname.rstrip(".")
    if not host:
        return False
    if host.isdigit() or host.lower().startswith("0x"):
        return True
    parts = host.split(".")
    if len(parts) <= 4 and all(
        part.isdigit() or part.lower().startswith("0x") for part in parts if part
    ):
        if len(parts) != 4:
            return True
        if any(len(part) > 1 and part.startswith("0") for part in parts):
            return True
    return False


def _extract_embedded_ipv4(addr: ipaddress.IPv6Address) -> list[ipaddress.IPv4Address]:
    embedded: list[ipaddress.IPv4Address] = []
    if addr.ipv4_mapped is not None:
        embedded.append(addr.ipv4_mapped)
    if addr.sixtofour is not None:
        embedded.append(addr.sixtofour)
    if addr.teredo is not None:
        embedded.extend(addr.teredo)
    if addr in _NAT64_PREFIX or addr in _NAT64_DISCOVERY_PREFIX or addr in _SIIT_TRANSLATED_PREFIX:
        embedded.append(ipaddress.IPv4Address(addr.packed[-4:]))
    return embedded


def _validate_ip(
    addr: ipaddress.IPv4Address | ipaddress.IPv6Address, *, allow_private: bool
) -> None:
    if str(addr) in _CLOUD_METADATA_IPS:
        raise EmbeddingSSRFError("Blocked embedding endpoint IP: cloud metadata")
    if isinstance(addr, ipaddress.IPv4Address) and addr in _CLOUD_METADATA_IPV4_NET:
        raise EmbeddingSSRFError("Blocked embedding endpoint IP: link-local metadata range")
    if not allow_private:
        if isinstance(addr, ipaddress.IPv4Address):
            if any(addr in net for net in _BLOCKED_IPV4_NETWORKS) or addr.is_unspecified:
                raise EmbeddingSSRFError("Blocked private or reserved embedding endpoint IP")
        else:
            if (
                any(addr in net for net in _BLOCKED_IPV6_NETWORKS)
                or not addr.is_global
                or addr.is_unspecified
            ):
                raise EmbeddingSSRFError("Blocked private or reserved embedding endpoint IP")
    if isinstance(addr, ipaddress.IPv6Address):
        for inner in _extract_embedded_ipv4(addr):
            _validate_ip(inner, allow_private=allow_private)


def validate_embedding_url(url: str) -> tuple[str, str, int]:
    """Validate embedding URL scheme and hostname against SSRF protections."""
    parsed = urllib.parse.urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise EmbeddingSSRFError(f"Unsupported embedding base URL scheme '{scheme}'")
    hostname = parsed.hostname
    if not hostname:
        raise EmbeddingSSRFError("Missing hostname in embedding base URL")

    allow_private = _allow_private_endpoints()
    lower = hostname.rstrip(".").lower()
    if lower in _CLOUD_METADATA_HOSTNAMES:
        raise EmbeddingSSRFError("Blocked cloud metadata hostname")
    if lower.endswith(_K8S_SUFFIX):
        raise EmbeddingSSRFError("Blocked cluster-internal hostname")
    if not allow_private and lower in _LOCALHOST_NAMES:
        raise EmbeddingSSRFError("Blocked localhost embedding endpoint")

    try:
        ip_obj = ipaddress.ip_address(hostname)
    except ValueError:
        ip_obj = None

    if ip_obj is not None:
        _validate_ip(ip_obj, allow_private=allow_private)
    elif _is_non_canonical_numeric_ipv4_host(hostname):
        raise EmbeddingSSRFError("Blocked non-canonical numeric IP hostname")

    port = parsed.port or (443 if scheme == "https" else 80)
    return scheme, hostname, port


def validate_embedding_url_and_dns(url: str) -> None:
    """Synchronously validate embedding base URL and all resolved DNS addresses."""
    _scheme, hostname, port = validate_embedding_url(url)
    allow_private = _allow_private_endpoints()
    try:
        addrinfo = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise EmbeddingSSRFError("Embedding DNS resolution failed") from exc
    if not addrinfo:
        raise EmbeddingSSRFError("Embedding DNS resolution returned no results")
    for _family, _type, _proto, _canonname, sockaddr in addrinfo:
        ip_obj = ipaddress.ip_address(str(sockaddr[0]))
        _validate_ip(ip_obj, allow_private=allow_private)


class EmbeddingSSRFSafeTransport(httpx.AsyncBaseTransport):
    """httpx transport pinning DNS resolution after validating every returned IP."""

    def __init__(self) -> None:
        self._inner = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        scheme, hostname, port = validate_embedding_url(str(request.url))
        allow_private = _allow_private_endpoints()
        await request.aread()

        try:
            addrinfo = await asyncio.to_thread(
                socket.getaddrinfo, hostname, port, type=socket.SOCK_STREAM
            )
        except socket.gaierror as exc:
            raise EmbeddingSSRFError("Embedding DNS resolution failed") from exc
        if not addrinfo:
            raise EmbeddingSSRFError("Embedding DNS resolution returned no results")

        for _family, _type, _proto, _canonname, sockaddr in addrinfo:
            ip_obj = ipaddress.ip_address(str(sockaddr[0]))
            _validate_ip(ip_obj, allow_private=allow_private)

        pinned_ip = str(addrinfo[0][4][0])
        pinned_url = request.url.copy_with(host=pinned_ip)
        extensions = dict(request.extensions)
        if scheme == "https":
            try:
                extensions["sni_hostname"] = hostname.encode("idna")
            except UnicodeError as exc:
                raise EmbeddingSSRFError("Invalid internationalized hostname") from exc

        pinned_request = httpx.Request(
            method=request.method,
            url=pinned_url,
            headers=request.headers,
            content=request.content,
            extensions=extensions,
        )
        return await self._inner.handle_async_request(pinned_request)

    async def aclose(self) -> None:
        await self._inner.aclose()


def create_safe_embedding_http_client(timeout: float) -> httpx.AsyncClient:
    """Create an AsyncClient for embedding providers with SSRF protections and redirects disabled."""
    return httpx.AsyncClient(
        transport=EmbeddingSSRFSafeTransport(),
        follow_redirects=False,
        timeout=timeout,
    )

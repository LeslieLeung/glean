"""
SSRF-safe httpx client.

Provides a drop-in replacement for ``httpx.AsyncClient`` that protects against
Server-Side Request Forgery (SSRF). The implementation is inspired by
``langchain_core._security`` but is fully self-contained (stdlib + httpx only).

For every outgoing request (including each redirect hop) the transport:

1. Validates the URL scheme against the policy.
2. Validates the hostname against blocked patterns (localhost, cloud metadata,
   Kubernetes internal DNS).
3. Resolves DNS and validates **all** returned IPs.
4. Rewrites the request to connect to a validated IP while preserving the
   original ``Host`` header and TLS SNI hostname.

Because DNS resolution, IP validation, and connection happen in a single code
path, this is resistant to DNS rebinding (TOCTOU) attacks. Redirects are
re-validated because ``follow_redirects`` is set on the client, causing
``handle_async_request`` to be invoked again for each redirect target.
"""

import asyncio
import dataclasses
import ipaddress
import logging
import os
import socket
import urllib.parse

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Blocklist constants
# ---------------------------------------------------------------------------

_BLOCKED_IPV4_NETWORKS: tuple[ipaddress.IPv4Network, ...] = tuple(
    ipaddress.IPv4Network(n)
    for n in (
        "10.0.0.0/8",  # RFC 1918 - private class A
        "172.16.0.0/12",  # RFC 1918 - private class B
        "192.168.0.0/16",  # RFC 1918 - private class C
        "127.0.0.0/8",  # RFC 1122 - loopback
        "169.254.0.0/16",  # RFC 3927 - link-local
        "0.0.0.0/8",  # RFC 1122 - "this network"
        "100.64.0.0/10",  # RFC 6598 - shared/CGN address space
        "192.0.0.0/24",  # RFC 6890 - IETF protocol assignments
        "192.0.2.0/24",  # RFC 5737 - TEST-NET-1 (documentation)
        "198.18.0.0/15",  # RFC 2544 - benchmarking
        "198.51.100.0/24",  # RFC 5737 - TEST-NET-2 (documentation)
        "203.0.113.0/24",  # RFC 5737 - TEST-NET-3 (documentation)
        "224.0.0.0/4",  # RFC 5771 - multicast
        "240.0.0.0/4",  # RFC 1112 - reserved for future use
        "255.255.255.255/32",  # RFC 919 - limited broadcast
    )
)

_BLOCKED_IPV6_NETWORKS: tuple[ipaddress.IPv6Network, ...] = tuple(
    ipaddress.IPv6Network(n)
    for n in (
        "::/128",  # RFC 4291 - unspecified
        "::1/128",  # RFC 4291 - loopback
        "fc00::/7",  # RFC 4193 - unique local addresses (ULA)
        "fe80::/10",  # RFC 4291 - link-local
        "ff00::/8",  # RFC 4291 - multicast
        "::ffff:0:0/96",  # RFC 4291 - IPv4-mapped IPv6 addresses
        "::ffff:0:0:0/96",  # RFC 2765 - SIIT IPv4-translated addresses
        "::0.0.0.0/96",  # RFC 4291 - IPv4-compatible IPv6 (deprecated)
        "64:ff9b::/96",  # RFC 6052 - NAT64 well-known prefix
        "64:ff9b:1::/48",  # RFC 8215 - NAT64 discovery prefix
        "100::/64",  # RFC 6666 - discard-only prefix
        "2001::/32",  # RFC 4380 - Teredo tunneling
        "2001:2::/48",  # RFC 5180 - benchmarking
        "2001:db8::/32",  # RFC 3849 - documentation
        "2002::/16",  # RFC 3056 - 6to4
    )
)

_CLOUD_METADATA_IPS: frozenset[str] = frozenset(
    {
        "169.254.169.254",  # AWS, GCP, Azure, DigitalOcean, Oracle Cloud
        "169.254.170.2",  # AWS ECS task metadata
        "169.254.170.23",  # AWS EKS Pod Identity Agent
        "100.100.100.200",  # Alibaba Cloud metadata
        "fd00:ec2::254",  # AWS EC2 IMDSv2 over IPv6 (Nitro instances)
        "fd00:ec2::23",  # AWS EKS Pod Identity Agent (IPv6)
        "fe80::a9fe:a9fe",  # OpenStack Nova metadata (IPv6 link-local)
    }
)

# Network ranges that are always blocked when block_cloud_metadata=True,
# independent of block_private_ips. The entire link-local range is used by
# cloud metadata services across providers.
_CLOUD_METADATA_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.IPv4Network("169.254.0.0/16"),
)

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

_LOOPBACK_IPV4 = ipaddress.IPv4Network("127.0.0.0/8")
_THIS_NETWORK_IPV4 = ipaddress.IPv4Network("0.0.0.0/8")
_LOOPBACK_IPV6 = ipaddress.IPv6Address("::1")

# NAT64 & SIIT prefixes
_NAT64_PREFIX = ipaddress.IPv6Network("64:ff9b::/96")
_NAT64_DISCOVERY_PREFIX = ipaddress.IPv6Network("64:ff9b:1::/48")
_SIIT_TRANSLATED_PREFIX = ipaddress.IPv6Network("::ffff:0:0:0/96")

DEFAULT_MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MiB

# Keys that AsyncHTTPTransport accepts (forwarded from factory kwargs).
_TRANSPORT_KWARGS: frozenset[str] = frozenset(
    {
        "verify",
        "cert",
        "trust_env",
        "http1",
        "http2",
        "limits",
        "retries",
    }
)


class SSRFBlockedError(httpx.ConnectError):
    """Raised when a request is blocked by the SSRF policy.

    Subclasses ``httpx.ConnectError`` (an ``httpx.RequestError``/``httpx.HTTPError``)
    so that callers already handling httpx errors fail closed without special
    casing, while still allowing explicit ``except SSRFBlockedError`` handling.
    """


class ResponseTooLargeError(httpx.RequestError):
    """Raised when a fetched HTTP response exceeds the configured byte limit."""


class InvalidContentTypeError(httpx.RequestError):
    """Raised when a fetched HTTP response does not match allowed MIME types."""


# ---------------------------------------------------------------------------
# SSRFPolicy
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class SSRFPolicy:
    """Immutable policy controlling which URLs/IPs are considered safe."""

    allowed_schemes: frozenset[str] = frozenset({"http", "https"})
    block_private_ips: bool = True
    block_localhost: bool = True
    block_cloud_metadata: bool = True
    block_k8s_internal: bool = True
    allowed_hosts: frozenset[str] = frozenset()
    additional_blocked_cidrs: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = ()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_embedded_ipv4(
    addr: ipaddress.IPv6Address,
) -> list[ipaddress.IPv4Address]:
    """Extract embedded IPv4 addresses from IPv4-mapped, 6to4, Teredo, SIIT, or NAT64 IPv6."""
    embedded: list[ipaddress.IPv4Address] = []
    if addr.ipv4_mapped is not None:
        embedded.append(addr.ipv4_mapped)
    if addr.sixtofour is not None:
        embedded.append(addr.sixtofour)
    if addr.teredo is not None:
        embedded.extend(addr.teredo)

    if addr in _NAT64_PREFIX or addr in _NAT64_DISCOVERY_PREFIX or addr in _SIIT_TRANSLATED_PREFIX:
        raw = addr.packed
        embedded.append(ipaddress.IPv4Address(raw[-4:]))

    return embedded


def _is_non_canonical_numeric_ipv4_host(hostname: str) -> bool:
    """Reject octal, hex, decimal-integer, or shorthand numeric IPv4 host literals."""
    host = hostname.rstrip(".")
    if not host:
        return False
    # Single integer or hex integer (e.g. 2130706433 or 0x7f000001)
    if host.isdigit() or host.lower().startswith("0x"):
        return True
    parts = host.split(".")
    if len(parts) <= 4 and all(
        part.isdigit() or part.lower().startswith("0x") for part in parts if part
    ):
        # Not already parsed as canonical IPv4 by ipaddress.ip_address -> shorthand or octal/hex.
        if len(parts) != 4:
            return True
        if any(len(part) > 1 and part.startswith("0") for part in parts):
            return True
    return False


def _ip_in_blocked_networks(
    addr: ipaddress.IPv4Address | ipaddress.IPv6Address,
    policy: SSRFPolicy,
) -> str | None:
    """Return a reason string if *addr* falls in a blocked range, else None."""
    if isinstance(addr, ipaddress.IPv4Address):
        if policy.block_private_ips:
            for net4 in _BLOCKED_IPV4_NETWORKS:
                if addr in net4:
                    return "private IP range"
        for extra in policy.additional_blocked_cidrs:
            if isinstance(extra, ipaddress.IPv4Network) and addr in extra:
                return "blocked CIDR"
    else:
        if policy.block_private_ips:
            for net6 in _BLOCKED_IPV6_NETWORKS:
                if addr in net6:
                    return "private IP range"
            if not addr.is_global:
                return "private IP range"
        for extra in policy.additional_blocked_cidrs:
            if isinstance(extra, ipaddress.IPv6Network) and addr in extra:
                return "blocked CIDR"

    # Loopback check - independent of block_private_ips so that
    # block_localhost=True still catches 127.x.x.x / ::1 / unspecified even when
    # private IPs are allowed.
    if policy.block_localhost:
        if isinstance(addr, ipaddress.IPv4Address) and (
            addr in _LOOPBACK_IPV4 or addr in _THIS_NETWORK_IPV4 or addr.is_unspecified
        ):
            return "localhost address"
        if isinstance(addr, ipaddress.IPv6Address) and (
            addr == _LOOPBACK_IPV6 or addr.is_unspecified
        ):
            return "localhost address"

    # Cloud metadata check - IP set *and* network ranges (e.g. 169.254.0.0/16).
    # Independent of block_private_ips so that allowing private IPs still blocks
    # cloud metadata endpoints.
    if policy.block_cloud_metadata:
        if str(addr) in _CLOUD_METADATA_IPS:
            return "cloud metadata endpoint"
        for meta_net in _CLOUD_METADATA_NETWORKS:
            if addr.version == meta_net.version and addr in meta_net:
                return "cloud metadata endpoint"

    return None


# ---------------------------------------------------------------------------
# Public validation functions
# ---------------------------------------------------------------------------


def validate_resolved_ip(ip_str: str, policy: SSRFPolicy) -> None:
    """Validate a resolved IP address against the SSRF policy.

    Raises:
        SSRFBlockedError: If the IP is blocked.
    """
    try:
        addr: ipaddress.IPv4Address | ipaddress.IPv6Address = ipaddress.ip_address(ip_str)
    except ValueError as exc:
        raise SSRFBlockedError("invalid IP address") from exc

    reason = _ip_in_blocked_networks(addr, policy)
    if reason is not None:
        raise SSRFBlockedError(reason)

    if isinstance(addr, ipaddress.IPv6Address):
        for inner in _extract_embedded_ipv4(addr):
            inner_reason = _ip_in_blocked_networks(inner, policy)
            if inner_reason is not None:
                raise SSRFBlockedError(inner_reason)


def validate_hostname(hostname: str, policy: SSRFPolicy) -> None:
    """Validate a hostname against the SSRF policy.

    Raises:
        SSRFBlockedError: If the hostname is blocked.
    """
    lower = hostname.rstrip(".").lower()

    if policy.block_localhost and lower in _LOCALHOST_NAMES:
        raise SSRFBlockedError("localhost address")

    if policy.block_cloud_metadata and lower in _CLOUD_METADATA_HOSTNAMES:
        raise SSRFBlockedError("cloud metadata endpoint")

    if policy.block_k8s_internal and lower.endswith(_K8S_SUFFIX):
        raise SSRFBlockedError("Kubernetes internal DNS")


def validate_url_sync(url: str, policy: SSRFPolicy) -> None:
    """Synchronous URL validation (no DNS resolution).

    Checks scheme and hostname patterns only. Literal IP hostnames are
    validated against the IP blocklist directly.

    Raises:
        SSRFBlockedError: If the URL violates the policy.
    """
    parsed = urllib.parse.urlparse(url)

    scheme = (parsed.scheme or "").lower()
    if scheme not in policy.allowed_schemes:
        raise SSRFBlockedError(f"scheme '{scheme}' not allowed")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFBlockedError("missing hostname")

    normalized_host = hostname.rstrip(".").lower()
    if normalized_host in {h.rstrip(".").lower() for h in policy.allowed_hosts}:
        return

    # If the hostname is a literal IP, validate it directly.
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        validate_resolved_ip(hostname, policy)
        return

    if _is_non_canonical_numeric_ipv4_host(hostname):
        raise SSRFBlockedError("non-canonical numeric IP hostname not allowed")

    validate_hostname(hostname, policy)


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------


class SSRFSafeTransport(httpx.AsyncBaseTransport):
    """httpx async transport that validates DNS results against an SSRF policy.

    For every outgoing request the transport validates the scheme/hostname,
    resolves DNS, validates every resolved IP, then pins the connection to a
    validated IP (preserving the original Host header and TLS SNI hostname).
    Redirects are re-validated on each hop because ``follow_redirects`` is set
    on the client.
    """

    def __init__(
        self,
        policy: SSRFPolicy,
        **transport_kwargs: object,
    ) -> None:
        self._policy = policy
        self._inner = httpx.AsyncHTTPTransport(**transport_kwargs)  # type: ignore[arg-type]

    async def handle_async_request(
        self,
        request: httpx.Request,
    ) -> httpx.Response:
        hostname = request.url.host or ""
        scheme = request.url.scheme.lower()

        # 1-3. Scheme, hostname, and literal-IP checks.
        try:
            validate_url_sync(str(request.url), self._policy)
        except SSRFBlockedError:
            logger.warning("Blocked SSRF request (url validation): %s", request.url)
            raise

        # Ensure the request body is buffered before forwarding or rebuilding
        # the request, because redirect hops arrive in streaming state.
        await request.aread()

        # Allowed-hosts bypass - skip DNS/IP validation entirely.
        if hostname.rstrip(".").lower() in {
            h.rstrip(".").lower() for h in self._policy.allowed_hosts
        }:
            return await self._inner.handle_async_request(request)

        # 4. DNS resolution.
        port = request.url.port or (443 if scheme == "https" else 80)
        try:
            addrinfo = await asyncio.to_thread(
                socket.getaddrinfo,
                hostname,
                port,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise SSRFBlockedError("DNS resolution failed") from exc

        if not addrinfo:
            raise SSRFBlockedError("DNS resolution returned no results")

        # 5. Validate ALL resolved IPs - any blocked means reject.
        for _family, _type, _proto, _canonname, sockaddr in addrinfo:
            ip_str = str(sockaddr[0])
            try:
                validate_resolved_ip(ip_str, self._policy)
            except SSRFBlockedError:
                logger.warning(
                    "Blocked SSRF request: %s resolved to blocked IP %s",
                    hostname,
                    ip_str,
                )
                raise

        # 6. Pin to first resolved IP.
        pinned_ip = str(addrinfo[0][4][0])

        # 7. Rewrite URL to use pinned IP, preserving Host header and SNI.
        pinned_url = request.url.copy_with(host=pinned_ip)

        extensions = dict(request.extensions)
        if scheme == "https":
            try:
                extensions["sni_hostname"] = hostname.encode("idna")
            except UnicodeError as exc:
                raise SSRFBlockedError("invalid internationalized hostname") from exc

        pinned_request = httpx.Request(
            method=request.method,
            url=pinned_url,
            headers=request.headers,  # Host header already set to original
            content=request.content,
            extensions=extensions,
        )

        return await self._inner.handle_async_request(pinned_request)

    async def aclose(self) -> None:
        await self._inner.aclose()


# ---------------------------------------------------------------------------
# Default policy (env-configurable for self-hosting)
# ---------------------------------------------------------------------------


def _env_flag(name: str) -> bool:
    """Return True if the env var is set to a truthy value."""
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _default_policy() -> SSRFPolicy:
    """Build the default policy, allowing self-hosters to opt into private access.

    Environment variables (secure defaults):
        SSRF_ALLOW_PRIVATE: if truthy, allow private IPs and localhost
            (cloud metadata endpoints remain blocked).
        SSRF_ALLOWED_HOSTS: comma-separated hostnames to allowlist (DNS/IP
            validation is skipped for these hosts).
    """
    allow_private = _env_flag("SSRF_ALLOW_PRIVATE")
    allowed_hosts_raw = os.environ.get("SSRF_ALLOWED_HOSTS", "")
    allowed_hosts = frozenset(h.strip().lower() for h in allowed_hosts_raw.split(",") if h.strip())

    return SSRFPolicy(
        block_private_ips=not allow_private,
        block_localhost=not allow_private,
        block_cloud_metadata=True,
        block_k8s_internal=True,
        allowed_hosts=allowed_hosts,
    )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def safe_async_client(
    policy: SSRFPolicy | None = None,
    **kwargs: object,
) -> httpx.AsyncClient:
    """Create an ``httpx.AsyncClient`` with SSRF protection.

    Drop-in replacement for ``httpx.AsyncClient(...)`` - callers just swap the
    constructor call. Transport-specific kwargs (``verify``, ``cert``,
    ``retries``, etc.) are forwarded to the inner ``AsyncHTTPTransport``;
    everything else goes to the ``AsyncClient``.

    Args:
        policy: SSRF policy to enforce. Defaults to an env-configurable policy
            that blocks private/loopback/link-local/cloud-metadata targets.
        **kwargs: Forwarded to the transport or client as appropriate.

    Returns:
        A configured ``httpx.AsyncClient`` with ``follow_redirects`` enabled so
        redirects are re-validated.
    """
    effective_policy = policy if policy is not None else _default_policy()

    transport_kwargs: dict[str, object] = {}
    client_kwargs: dict[str, object] = {}
    for key, value in kwargs.items():
        if key in _TRANSPORT_KWARGS:
            transport_kwargs[key] = value
        else:
            client_kwargs[key] = value

    transport = SSRFSafeTransport(policy=effective_policy, **transport_kwargs)

    # Apply defaults only if not overridden by caller.
    client_kwargs.setdefault("follow_redirects", True)
    client_kwargs.setdefault("max_redirects", 10)

    return httpx.AsyncClient(
        transport=transport,
        **client_kwargs,  # type: ignore[arg-type]
    )


async def safe_fetch_bytes(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    allowed_content_types: tuple[str, ...] | None = None,
    return_on_304: bool = False,
) -> tuple[bytes, httpx.Response]:
    """Stream an HTTP GET response and enforce Content-Type and byte size limits.

    Protects against unbounded response buffering and gzip decompression bombs
    by tracking decompressed bytes incrementally via ``response.aiter_bytes()``.
    """
    async with client.stream("GET", url) as response:
        if return_on_304 and response.status_code == 304:
            return b"", response

        response.raise_for_status()

        if allowed_content_types is not None:
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if not any(allowed in content_type for allowed in allowed_content_types):
                raise InvalidContentTypeError(
                    f"Unsupported content-type '{content_type or 'unknown'}'",
                    request=response.request,
                )

        content_length_raw = response.headers.get("content-length")
        if content_length_raw is not None:
            try:
                if int(content_length_raw) > max_bytes:
                    raise ResponseTooLargeError(
                        f"Response Content-Length exceeds {max_bytes} bytes",
                        request=response.request,
                    )
            except ValueError:
                pass

        chunks: list[bytes] = []
        total_bytes = 0
        async for chunk in response.aiter_bytes():
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                raise ResponseTooLargeError(
                    f"Response body exceeds {max_bytes} bytes limit",
                    request=response.request,
                )
            chunks.append(chunk)

        return b"".join(chunks), response

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
        "::1/128",  # RFC 4291 - loopback
        "fc00::/7",  # RFC 4193 - unique local addresses (ULA)
        "fe80::/10",  # RFC 4291 - link-local
        "ff00::/8",  # RFC 4291 - multicast
        "::ffff:0:0/96",  # RFC 4291 - IPv4-mapped IPv6 addresses
        "::0.0.0.0/96",  # RFC 4291 - IPv4-compatible IPv6 (deprecated)
        "64:ff9b::/96",  # RFC 6052 - NAT64 well-known prefix
        "64:ff9b:1::/48",  # RFC 8215 - NAT64 discovery prefix
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

# NAT64 well-known prefixes
_NAT64_PREFIX = ipaddress.IPv6Network("64:ff9b::/96")
_NAT64_DISCOVERY_PREFIX = ipaddress.IPv6Network("64:ff9b:1::/48")

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
) -> ipaddress.IPv4Address | None:
    """Extract an embedded IPv4 from IPv4-mapped or NAT64 IPv6 addresses."""
    # Check ipv4_mapped first (covers ::ffff:x.x.x.x)
    if addr.ipv4_mapped is not None:
        return addr.ipv4_mapped

    # Check NAT64 prefixes - embedded IPv4 is in the last 4 bytes
    if addr in _NAT64_PREFIX or addr in _NAT64_DISCOVERY_PREFIX:
        raw = addr.packed
        return ipaddress.IPv4Address(raw[-4:])

    return None


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
        for extra in policy.additional_blocked_cidrs:
            if isinstance(extra, ipaddress.IPv6Network) and addr in extra:
                return "blocked CIDR"

    # Loopback check - independent of block_private_ips so that
    # block_localhost=True still catches 127.x.x.x / ::1 even when
    # private IPs are allowed.
    if policy.block_localhost:
        if isinstance(addr, ipaddress.IPv4Address) and (
            addr in _LOOPBACK_IPV4 or addr in _THIS_NETWORK_IPV4
        ):
            return "localhost address"
        if isinstance(addr, ipaddress.IPv6Address) and addr == _LOOPBACK_IPV6:
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

    if isinstance(addr, ipaddress.IPv6Address):
        inner = _extract_embedded_ipv4(addr)
        if inner is not None:
            addr = inner

    reason = _ip_in_blocked_networks(addr, policy)
    if reason is not None:
        raise SSRFBlockedError(reason)


def validate_hostname(hostname: str, policy: SSRFPolicy) -> None:
    """Validate a hostname against the SSRF policy.

    Raises:
        SSRFBlockedError: If the hostname is blocked.
    """
    lower = hostname.lower()

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

    if hostname.lower() in {h.lower() for h in policy.allowed_hosts}:
        return

    # If the hostname is a literal IP, validate it directly.
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        validate_resolved_ip(hostname, policy)
        return

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

        # Allowed-hosts bypass - skip DNS/IP validation entirely.
        if hostname.lower() in {h.lower() for h in self._policy.allowed_hosts}:
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
            extensions["sni_hostname"] = hostname.encode("ascii")

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
        GLEAN_SSRF_ALLOW_PRIVATE: if truthy, allow private IPs and localhost
            (cloud metadata endpoints remain blocked).
        GLEAN_SSRF_ALLOWED_HOSTS: comma-separated hostnames to allowlist (DNS/IP
            validation is skipped for these hosts).
    """
    allow_private = _env_flag("GLEAN_SSRF_ALLOW_PRIVATE")
    allowed_hosts_raw = os.environ.get("GLEAN_SSRF_ALLOWED_HOSTS", "")
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

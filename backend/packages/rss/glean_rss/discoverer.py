"""
RSS feed discovery.

Discovers RSS/Atom feeds from websites.
"""

import re
from collections.abc import Iterable
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from .parser import parse_feed
from .safe_http import safe_async_client

# MIME types accepted by RSSHub-Radar's getPageRSS. Charset parameters are
# stripped before comparison. Generic XML is handled separately: Radar skips
# it, but sites advertise real feeds as application/xml (for example
# /updates.xml). Those links are fetched, and parsing rejects sitemaps.
_GENERIC_XML_MIME_TYPES = frozenset({"application/xml", "text/xml"})
_FEED_MIME_TYPES = frozenset(
    {
        "application/rss+xml",
        "application/atom+xml",
        "application/rdf+xml",
        "application/rss",
        "application/atom",
        "application/rdf",
        "text/rss+xml",
        "text/atom+xml",
        "text/rdf+xml",
        "text/rss",
        "text/atom",
        "text/rdf",
        "application/feed+json",
    }
)

# /(feed|rss|atom)(.(xml|rss|atom))?/?$
_FEED_PATH_RE = re.compile(r"/(?:feed|rss|atom)(?:\.(?:xml|rss|atom))?$", re.IGNORECASE)
# An "rss" token in a title or class, including icon classes such as i-ri-rss-fill.
_RSS_TOKEN_RE = re.compile(r"(?:^|[^a-zA-Z])rss(?:[^a-zA-Z]|$)", re.IGNORECASE)
_FEED_TEXT_RE = re.compile(
    r"^\s*(?:subscribe\s+(?:via|to)\s+)?(?:rss|atom|feed)(?:\s+feed)?\s*$",
    re.IGNORECASE,
)
_FEED_QUERY_RE = re.compile(r"(?:^|&)(?:feed|format)=(rss2?|atom|rdf|xml)(?:&|$)", re.IGNORECASE)
_COMMON_FEED_SUFFIXES = ("feed.xml", "rss.xml", "atom.xml", "index.xml", "feed", "rss", "atom")
_MAX_PAGE_CANDIDATES = 6
_MAX_CANDIDATES = 8


async def discover_feed(url: str, timeout: int = 30) -> tuple[str, str]:
    """
    Discover RSS feed URL from a given URL.

    Tries to:
    1. Parse the URL itself as RSS, Atom, or JSON Feed
    2. Follow autodiscovery ``<link>`` tags and ``feed:`` URLs
    3. Follow anchors whose path, title, class, or text marks a feed
    4. Probe conventional feed paths such as ``/feed.xml``

    Args:
        url: URL to discover feed from.
        timeout: Request timeout in seconds.

    Returns:
        Tuple of (feed_url, feed_title).

    Raises:
        ValueError: If no feed found or request fails.
    """
    async with safe_async_client(
        timeout=timeout, follow_redirects=True, headers={"User-Agent": "Glean/1.0"}
    ) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
        except (httpx.HTTPError, httpx.InvalidURL) as e:
            raise ValueError(f"Failed to fetch URL: {e}") from e

        # Validate content, even when a server uses an incorrect MIME type.
        final_url = str(response.url)
        try:
            feed = await parse_feed(response.text, final_url)
            return final_url, feed.title
        except ValueError:
            pass

        content_type = response.headers.get("content-type", "").lower()
        if not _should_scan_html(content_type, response.text):
            raise ValueError("No RSS feed found at this URL")

        soup = BeautifulSoup(response.content, "lxml")
        for candidate in _candidate_feed_urls(soup, final_url):
            found = await _fetch_feed(client, candidate)
            if found is not None:
                return found

        raise ValueError("No RSS feed found at this URL")


async def fetch_feed(
    url: str, etag: str | None = None, last_modified: str | None = None
) -> tuple[str, dict[str, str]] | None:
    """
    Fetch feed content with conditional request support.

    Args:
        url: Feed URL.
        etag: Optional ETag for conditional request.
        last_modified: Optional Last-Modified for conditional request.

    Returns:
        Tuple of (content, headers) if modified, None if not modified (304).

    Raises:
        ValueError: If request fails.
    """
    headers = {"User-Agent": "Glean/1.0"}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    async with safe_async_client(timeout=30, follow_redirects=True, headers=headers) as client:
        try:
            response = await client.get(url)

            if response.status_code == 304:
                # Not modified
                return None

            response.raise_for_status()

            # Extract caching headers
            cache_headers: dict[str, str] = {}
            if "etag" in response.headers:
                cache_headers["etag"] = response.headers["etag"]
            if "last-modified" in response.headers:
                cache_headers["last-modified"] = response.headers["last-modified"]

            return response.text, cache_headers

        except (httpx.HTTPError, httpx.InvalidURL) as e:
            raise ValueError(f"Failed to fetch feed: {e}") from e


async def _fetch_feed(client: httpx.AsyncClient, url: str) -> tuple[str, str] | None:
    """Fetch and parse one candidate. Returns None when it is not a feed."""
    try:
        response = await client.get(url)
        response.raise_for_status()
        feed = await parse_feed(response.text, str(response.url))
    except (httpx.HTTPError, ValueError):
        return None
    return str(response.url), feed.title


def _should_scan_html(content_type: str, body: str) -> bool:
    """Return whether the response should be scanned for feed links."""
    if "html" in content_type or not content_type:
        return True
    sample = body.lstrip()[:200].lower()
    return sample.startswith(("<!doctype html", "<html")) or "<head" in sample


def _candidate_feed_urls(soup: BeautifulSoup, base_url: str) -> list[str]:
    """
    Build an ordered, de-duplicated list of feed URLs to try.

    Explicit autodiscovery comes first, then same-site anchors, then feed
    links that point at another host. Conventional paths are last: a page
    such as ``/blog/`` has fourteen of them, and appending external anchors
    after that list would drop the advertised feed once the list is capped.
    """
    autodiscovery: list[str] = []
    same_origin: list[str] = []
    external: list[str] = []

    for link in soup.find_all("link"):
        href = _href(link)
        if href is None or not _link_advertises_feed(link, base_url, href):
            continue
        _append_unique(autodiscovery, _absolute_http_url(base_url, href), base_url)

    for anchor in soup.find_all("a"):
        href = _href(anchor)
        if href is None:
            continue
        absolute = _absolute_http_url(base_url, href)
        if absolute is None or not _anchor_advertises_feed(anchor, absolute):
            continue
        bucket = same_origin if _same_origin(absolute, base_url) else external
        _append_unique(bucket, absolute, base_url)

    page_candidates = _dedupe([*autodiscovery, *same_origin])[:_MAX_PAGE_CANDIDATES]
    conventional = [
        candidate
        for suffix in _COMMON_FEED_SUFFIXES
        for candidate in _conventional_urls(base_url, suffix)
        if not _same_document(candidate, base_url)
    ]
    return _dedupe([*page_candidates, *external, *conventional])[:_MAX_CANDIDATES]


def _link_advertises_feed(link: Tag, base_url: str, href: str) -> bool:
    """Return whether a link element is an RSS, Atom, JSON Feed, or generic XML link."""
    mime = _attr_text(link, "type").lower().split(";", 1)[0].strip()
    if (
        mime in _FEED_MIME_TYPES
        or mime in _GENERIC_XML_MIME_TYPES
        or "rss" in mime
        or "atom" in mime
    ):
        return True
    rel = _attr_text(link, "rel").lower()
    absolute = _absolute_http_url(base_url, href)
    return "alternate" in rel.split() and absolute is not None and _looks_like_feed_url(absolute)


def _anchor_advertises_feed(anchor: Tag, url: str) -> bool:
    """Return whether an anchor matches RSSHub-Radar's in-page feed rules."""
    if _looks_like_feed_url(url):
        return True
    if _RSS_TOKEN_RE.search(_attr_text(anchor, "title")):
        return True
    if _RSS_TOKEN_RE.search(_attr_text(anchor, "aria-label")):
        return True
    if _RSS_TOKEN_RE.search(_attr_text(anchor, "class")):
        return True
    for child in anchor.find_all(True, limit=4):
        if _RSS_TOKEN_RE.search(_attr_text(child, "class")) or _RSS_TOKEN_RE.search(
            _attr_text(child, "aria-label")
        ):
            return True
    return _FEED_TEXT_RE.match(anchor.get_text(" ", strip=True)) is not None


def _looks_like_feed_url(url: str) -> bool:
    """Return whether a URL path or query uses a conventional feed location."""
    parsed = urlparse(url)
    path = parsed.path.lower().rstrip("/") or "/"
    if _FEED_PATH_RE.search(path):
        return True
    return _FEED_QUERY_RE.search(parsed.query.lower()) is not None


def _conventional_urls(base_url: str, suffix: str) -> list[str]:
    """Return page-relative and origin-level candidates for one feed suffix."""
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        return []
    directory = base_url if base_url.endswith("/") else urljoin(base_url, ".")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return [urljoin(directory, suffix), f"{origin}/{suffix}"]


def _absolute_http_url(base_url: str, href: str) -> str | None:
    """Resolve href against base_url and keep only http(s) URLs without fragments."""
    stripped = _without_feed_scheme(href.strip())
    if not stripped or stripped.startswith(("#", "mailto:", "javascript:")):
        return None
    try:
        absolute = urljoin(base_url, stripped).split("#", 1)[0]
        parsed = urlparse(absolute)
    except ValueError:
        # urljoin rejects malformed targets such as "http://[broken".
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return absolute


def _without_feed_scheme(href: str) -> str:
    """Turn ``feed://`` and ``feed:`` prefixes into a normal URL, as RSSHub-Radar does."""
    lower = href.lower()
    if lower.startswith("feed://"):
        return "https://" + href[7:]
    if lower.startswith("feed:"):
        return href[5:]
    return href


def _same_origin(url: str, base_url: str) -> bool:
    candidate = urlparse(url)
    base = urlparse(base_url)
    return candidate.scheme == base.scheme and candidate.netloc.lower() == base.netloc.lower()


def _same_document(url: str, base_url: str) -> bool:
    return _dedupe_key(url) == _dedupe_key(base_url)


def _dedupe_key(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return parsed._replace(path=path, fragment="").geturl()


def _attr_text(tag: Tag, name: str) -> str:
    value = tag.get(name)
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return ""


def _href(tag: Tag) -> str | None:
    value = tag.get("href")
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        return str(value[0])
    return None


def _append_unique(urls: list[str], url: str | None, base_url: str) -> None:
    if (
        url
        and not _same_document(url, base_url)
        and _dedupe_key(url) not in {_dedupe_key(existing) for existing in urls}
    ):
        urls.append(url)


def _dedupe(urls: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for url in urls:
        key = _dedupe_key(url)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(url)
    return ordered

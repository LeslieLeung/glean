"""
RSS/Atom feed parser.

Parses RSS and Atom feeds using feedparser.
"""

import html
import json
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import urlparse

import feedparser
from feedparser import FeedParserDict


def _get_favicon_url(site_url: str | None) -> str | None:
    """
    Generate favicon URL from site URL.

    Args:
        site_url: Website URL.

    Returns:
        Favicon URL or None if site_url is invalid.
    """
    if not site_url:
        return None

    try:
        parsed = urlparse(site_url)
        if not parsed.scheme or not parsed.netloc:
            return None

        # Use Google's favicon service for reliable favicon fetching
        domain = parsed.netloc
        return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"
    except Exception:
        return None


class ParsedFeed:
    """Parsed feed metadata."""

    title: str
    description: str
    site_url: str
    language: str | None
    icon_url: str | None
    entries: list["ParsedEntry"]

    def __init__(self, data: FeedParserDict):
        """
        Initialize from feedparser data.

        Args:
            data: Parsed feed data from feedparser.
        """
        # feedparser returns a FeedParserDict for the "feed" key
        feed_info: dict[str, Any] = dict(data.get("feed", {}))  # type: ignore[arg-type]
        self.title = html.unescape(str(feed_info.get("title", "")))
        self.description = html.unescape(str(feed_info.get("description", "")))
        self.site_url = str(feed_info.get("link", ""))
        self.language = feed_info.get("language")

        # Try to get icon from feed, fallback to favicon
        icon = feed_info.get("icon") or feed_info.get("logo")
        self.icon_url = str(icon) if icon else _get_favicon_url(self.site_url)

        # Get entries with proper type handling
        entries_data: list[dict[str, Any]] = list(data.get("entries", []))  # type: ignore[arg-type]
        self.entries = [ParsedEntry(entry) for entry in entries_data]


class ParsedEntry:
    """Parsed entry data."""

    def __init__(self, data: dict[str, Any]):
        """
        Initialize from feedparser entry data.

        Args:
            data: Entry data from feedparser.
        """
        self.guid = data.get("id") or data.get("link", "")
        self.url = data.get("link", "")
        # Decode HTML entities in title
        raw_title = data.get("title", "")
        self.title = html.unescape(raw_title) if raw_title else ""
        self.author = data.get("author")
        self.summary = data.get("summary")

        # Get content (prefer content over summary)
        # Track whether the feed provides actual content or just summary/description
        content_list = data.get("content", [])
        if content_list:
            self.content = content_list[0].get("value")
            self.has_full_content = True  # Feed provides content field
        else:
            self.content = data.get("summary")
            self.has_full_content = (
                False  # Only has summary/description, may need full-text extraction
            )

        # Parse published date
        published = data.get("published_parsed") or data.get("updated_parsed")
        if published:
            try:
                self.published_at = datetime(*published[:6], tzinfo=UTC)
            except (TypeError, ValueError):
                self.published_at = None
        else:
            self.published_at = None


def _mapping(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    raw = cast(dict[object, object], value)
    return {str(key): item for key, item in raw.items()}


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _plain_text_as_html(text: str) -> str:
    """Escape plain text so it can be stored and rendered as HTML."""
    escaped = html.escape(text, quote=False)
    return escaped.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>\n")


def _parsed_time(value: object) -> tuple[int, ...] | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    utc = parsed.astimezone(UTC)
    return (utc.year, utc.month, utc.day, utc.hour, utc.minute, utc.second)


def _author_name(value: object) -> str | None:
    mapped = _mapping(value)
    if mapped is None:
        return None
    name = mapped.get("name")
    return name if isinstance(name, str) else None


def _json_author(item: dict[str, object]) -> str | None:
    authors = item.get("authors")
    if isinstance(authors, list):
        for author in cast(list[object], authors):
            name = _author_name(author)
            if name:
                return name
    return _author_name(item.get("author"))


def _parse_json_feed(content: str) -> ParsedFeed | None:
    """Parse a JSON Feed document. Returns None when the body is not one."""
    if not content.lstrip().startswith("{"):
        return None
    try:
        payload = _mapping(cast(object, json.loads(content)))
    except json.JSONDecodeError:
        return None
    if payload is None:
        return None
    version = payload.get("version")
    if not isinstance(version, str) or "jsonfeed.org" not in version:
        return None

    content_items: list[dict[str, Any]] = []
    raw_items = payload.get("items")
    if isinstance(raw_items, list):
        for index, raw_item in enumerate(cast(list[object], raw_items)):
            item = _mapping(raw_item)
            if item is None:
                continue
            entry: dict[str, Any] = {
                "id": _text(item.get("id")) or _text(item.get("url")) or f"item-{index}",
                "link": _text(item.get("url")) or _text(item.get("external_url")),
                "title": _text(item.get("title")),
                "author": _json_author(item),
                "summary": _text(item.get("summary")) or _text(item.get("content_text")),
            }
            html_content = _text(item.get("content_html"))
            text_content = _text(item.get("content_text"))
            if html_content:
                entry["content"] = [{"value": html_content}]
            elif text_content:
                entry["content"] = [{"value": _plain_text_as_html(text_content)}]
            published = _parsed_time(item.get("date_published")) or _parsed_time(
                item.get("date_modified")
            )
            if published:
                entry["published_parsed"] = published
            content_items.append(entry)

    feed_info: dict[str, Any] = {
        "title": _text(payload.get("title")),
        "description": _text(payload.get("description")),
        "link": _text(payload.get("home_page_url")) or _text(payload.get("feed_url")),
        "language": payload.get("language") if isinstance(payload.get("language"), str) else None,
        "icon": _text(payload.get("icon")) or _text(payload.get("favicon")),
    }
    parsed: dict[str, Any] = {"feed": feed_info, "entries": content_items}
    return ParsedFeed(parsed)  # type: ignore[arg-type]


async def parse_feed(content: str, url: str) -> ParsedFeed:
    """
    Parse RSS, Atom, or JSON Feed content.

    Args:
        content: Feed document.
        url: Feed URL (used for relative link resolution).

    Returns:
        Parsed feed data.

    Raises:
        ValueError: If feed parsing fails.
    """
    json_feed = _parse_json_feed(content)
    if json_feed is not None:
        return json_feed

    data: FeedParserDict = feedparser.parse(content)  # type: ignore[reportUnknownMemberType]

    if not data.get("version"):  # type: ignore[reportUnknownMemberType]
        raise ValueError("The URL does not contain an RSS or Atom feed")

    bozo: bool = bool(data.get("bozo", False))  # type: ignore[reportUnknownMemberType]
    entries: Any = data.get("entries")  # type: ignore[reportUnknownMemberType]
    if bozo and not entries:
        # Feed has errors and no entries
        raise ValueError(f"Failed to parse feed: {data.get('bozo_exception', 'Unknown error')}")

    return ParsedFeed(data)

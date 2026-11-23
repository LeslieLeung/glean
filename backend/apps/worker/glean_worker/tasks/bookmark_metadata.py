"""
Bookmark metadata fetching tasks.

Background tasks for fetching webpage title, description, and full content for URL bookmarks.
"""

import re
from typing import Any

from sqlalchemy import select

from glean_core import get_logger
from glean_database.models import Bookmark
from glean_database.session import get_session_context
from glean_rss import extract_fulltext, safe_async_client

logger = get_logger(__name__)

# Default user agent to avoid being blocked
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def extract_title(html: str) -> str | None:
    """
    Extract title from HTML content.

    Args:
        html: Raw HTML content.

    Returns:
        Extracted title or None if not found.
    """
    # Try <title> tag first
    title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    if title_match:
        return title_match.group(1).strip()

    # Try og:title meta tag
    og_title_match = re.search(
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if og_title_match:
        return og_title_match.group(1).strip()

    # Try reverse order (content before property)
    og_title_match2 = re.search(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']',
        html,
        re.IGNORECASE,
    )
    if og_title_match2:
        return og_title_match2.group(1).strip()

    return None


def extract_description(html: str) -> str | None:
    """
    Extract description from HTML content.

    Args:
        html: Raw HTML content.

    Returns:
        Extracted description or None if not found.
    """
    # Try meta description first
    desc_match = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if desc_match:
        return desc_match.group(1).strip()

    # Try reverse order (content before name)
    desc_match2 = re.search(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
        html,
        re.IGNORECASE,
    )
    if desc_match2:
        return desc_match2.group(1).strip()

    # Try og:description meta tag
    og_desc_match = re.search(
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if og_desc_match:
        return og_desc_match.group(1).strip()

    # Try reverse order (content before property)
    og_desc_match2 = re.search(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
        html,
        re.IGNORECASE,
    )
    if og_desc_match2:
        return og_desc_match2.group(1).strip()

    return None


def unescape_html(text: str) -> str:
    """
    Unescape common HTML entities.

    Args:
        text: Text with HTML entities.

    Returns:
        Unescaped text.
    """
    replacements = [
        ("&amp;", "&"),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&quot;", '"'),
        ("&#39;", "'"),
        ("&apos;", "'"),
        ("&#x27;", "'"),
        ("&nbsp;", " "),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


async def fetch_bookmark_metadata_task(
    _ctx: dict[str, Any], bookmark_id: str
) -> dict[str, str | int | None]:
    """Fetch content without overwriting edits made while the request was in flight."""
    async with get_session_context() as session:
        bookmark = await session.get(Bookmark, bookmark_id)
        if not bookmark or not bookmark.url:
            return {"status": "skipped"}
        url = bookmark.url
        bookmark.snapshot_status = "processing"
        await session.commit()
        title = description = content = None
        failed = False
        try:
            async with safe_async_client(
                timeout=30.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                if "text/html" not in response.headers.get("content-type", "").lower():
                    failed = True
                else:
                    title = extract_title(response.text)
                    description = extract_description(response.text)
                    content = await extract_fulltext(response.text, url=url)
        except Exception:
            logger.exception("Failed to fetch bookmark content", extra={"bookmark_id": bookmark_id})
            failed = True
        # Re-read under a lock after network I/O; concurrent edits and deletion win.
        bookmark = await session.scalar(
            select(Bookmark)
            .where(Bookmark.id == bookmark_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if not bookmark:
            return {"status": "skipped"}
        if title and not bookmark.title_edited:
            bookmark.title = unescape_html(title)[:500]
        if description and not bookmark.excerpt_edited:
            bookmark.excerpt = unescape_html(description)
        if content and not bookmark.content:
            bookmark.content = content
        bookmark.snapshot_status = "failed" if failed else "done"
        return {"status": "error" if failed else "success", "bookmark_id": bookmark_id}

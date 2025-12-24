"""
Bookmark metadata fetching tasks.

Background tasks for fetching webpage title, description, and full content for URL bookmarks.
"""

import re
from typing import Any

import httpx
from sqlalchemy import select

from glean_core import get_logger
from glean_database.models import Bookmark
from glean_database.session import get_session_context
from glean_rss import extract_fulltext

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
    """
    Fetch webpage metadata (title and description) for a bookmark.

    Args:
        _ctx: Worker context (unused).
        bookmark_id: Bookmark identifier.

    Returns:
        Dictionary with fetch results.
    """
    logger.info(
        "Starting metadata fetch",
        extra={"bookmark_id": bookmark_id},
    )

    async with get_session_context() as session:
        try:
            # Get bookmark from database
            stmt = select(Bookmark).where(Bookmark.id == bookmark_id)
            result = await session.execute(stmt)
            bookmark = result.scalar_one_or_none()

            if not bookmark:
                logger.error("Bookmark not found", extra={"bookmark_id": bookmark_id})
                return {"status": "error", "message": "Bookmark not found"}

            if not bookmark.url:
                logger.error("Bookmark has no URL", extra={"bookmark_id": bookmark_id})
                return {"status": "error", "message": "Bookmark has no URL"}

            logger.info("Fetching URL", extra={"bookmark_id": bookmark_id, "url": bookmark.url})

            # Fetch the webpage
            async with httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                response = await client.get(bookmark.url)
                response.raise_for_status()

                # Only process HTML content
                content_type = response.headers.get("content-type", "")
                if "text/html" not in content_type.lower():
                    logger.warning(
                        "Non-HTML content type",
                        extra={"bookmark_id": bookmark_id, "content_type": content_type},
                    )
                    return {
                        "status": "skipped",
                        "message": f"Non-HTML content: {content_type}",
                    }

                html = response.text

            # Extract metadata
            title = extract_title(html)
            description = extract_description(html)

            # Unescape HTML entities
            if title:
                title = unescape_html(title)
            if description:
                description = unescape_html(description)

            # Extract full content using readability
            content = None
            try:
                content = await extract_fulltext(html, url=bookmark.url)
                if content:
                    logger.info(
                        "Extracted content",
                        extra={"bookmark_id": bookmark_id, "content_length": len(content)},
                    )
                else:
                    logger.warning(
                        "Content extraction returned empty", extra={"bookmark_id": bookmark_id}
                    )
            except Exception as extract_err:
                logger.warning(
                    "Content extraction failed",
                    extra={"bookmark_id": bookmark_id, "error": str(extract_err)},
                )

            logger.debug(
                "Extracted metadata",
                extra={
                    "bookmark_id": bookmark_id,
                    "title": title,
                    "description_preview": description[:100] if description else None,
                },
            )

            # Update bookmark if we got better data
            updated = False

            # Update title if current title is just the URL
            if title and bookmark.title == bookmark.url:
                bookmark.title = title[:500]  # Respect max length
                updated = True
                logger.info("Updated title", extra={"bookmark_id": bookmark_id})

            # Update excerpt if not set
            if description and not bookmark.excerpt:
                bookmark.excerpt = description
                updated = True
                logger.info("Updated excerpt", extra={"bookmark_id": bookmark_id})

            # Store extracted content for in-app reading
            if content:
                bookmark.content = content
                updated = True
                logger.info("Updated content", extra={"bookmark_id": bookmark_id})

            if updated:
                logger.info("Successfully updated bookmark", extra={"bookmark_id": bookmark_id})
            else:
                logger.debug("No updates needed", extra={"bookmark_id": bookmark_id})

            return {
                "status": "success",
                "bookmark_id": bookmark_id,
                "title": title,
                "description": description[:200] if description else None,
                "content_length": len(content) if content else 0,
            }

        except httpx.HTTPStatusError as e:
            logger.error(
                "HTTP error fetching bookmark",
                extra={"bookmark_id": bookmark_id, "status_code": e.response.status_code},
            )
            return {
                "status": "error",
                "message": f"HTTP {e.response.status_code}",
            }
        except httpx.RequestError as e:
            logger.error(
                "Request error fetching bookmark",
                extra={"bookmark_id": bookmark_id, "error": str(e)},
            )
            return {"status": "error", "message": str(e)}
        except Exception:
            logger.exception(
                "Failed to fetch metadata",
                extra={"bookmark_id": bookmark_id},
            )
            raise

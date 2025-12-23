"""
Full-text content extractor.

Uses readability-lxml (Mozilla's Readability algorithm) to extract main content from web pages.
"""

import re
from typing import cast
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from readability import Document


def _is_relative_url(url: str) -> bool:
    """Check if a URL is relative."""
    parsed = urlparse(url)
    return not parsed.scheme and not parsed.netloc


def _escape_html_in_backticks(html: str) -> str:
    """
    Escape HTML special characters inside backtick-wrapped text.

    This prevents BeautifulSoup from interpreting code examples like `<img>`
    as actual HTML elements.
    """

    def escape_match(match: re.Match[str]) -> str:
        content = match.group(1)
        # Escape HTML special characters
        escaped = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f"`{escaped}`"

    return re.sub(r"`([^`]+)`", escape_match, html)


def postprocess_html(html: str, base_url: str | None = None) -> str:
    """
    Post-process extracted HTML to fix common issues.

    - Converts relative URLs to absolute URLs for images and links
    - Converts backtick-wrapped text to <code> tags

    Args:
        html: Extracted HTML content.
        base_url: Base URL for resolving relative paths.

    Returns:
        Processed HTML content.
    """
    # First, escape HTML inside backticks to prevent them from being parsed as tags
    html = _escape_html_in_backticks(html)

    soup = BeautifulSoup(html, "html.parser")

    # Fix relative URLs for images
    if base_url:
        for img in soup.find_all("img"):
            src = img.get("src")
            if isinstance(src, str) and _is_relative_url(src):
                img["src"] = urljoin(base_url, src)
            # Also handle data-src for lazy-loaded images
            data_src = img.get("data-src")
            if isinstance(data_src, str) and _is_relative_url(data_src):
                img["data-src"] = urljoin(base_url, data_src)
                # If src is missing or a placeholder, use data-src
                if not src or (isinstance(src, str) and ("data:" in src or "placeholder" in src)):
                    img["src"] = urljoin(base_url, data_src)
            # Handle srcset attribute on img elements (used by Astro, responsive images, etc.)
            img_srcset = img.get("srcset")
            if isinstance(img_srcset, str):
                img_srcset_parts = img_srcset.split(",")
                img_srcset_fixed: list[str] = []
                for img_srcset_part in img_srcset_parts:
                    img_srcset_part = img_srcset_part.strip()
                    if img_srcset_part:
                        img_url_parts = img_srcset_part.split()
                        if img_url_parts and _is_relative_url(img_url_parts[0]):
                            img_url_parts[0] = urljoin(base_url, img_url_parts[0])
                        img_srcset_fixed.append(" ".join(img_url_parts))
                img["srcset"] = ", ".join(img_srcset_fixed)

        # Fix relative URLs for links
        for a in soup.find_all("a"):
            href = a.get("href")
            if isinstance(href, str) and _is_relative_url(href):
                a["href"] = urljoin(base_url, href)

        # Fix relative URLs for source tags (picture elements)
        for source in soup.find_all("source"):
            source_srcset = source.get("srcset")
            if isinstance(source_srcset, str) and _is_relative_url(source_srcset.split()[0]):
                # srcset can have multiple URLs with sizes, handle them all
                source_parts = source_srcset.split(",")
                source_fixed_parts: list[str] = []
                for source_part in source_parts:
                    source_part = source_part.strip()
                    if source_part:
                        source_url_parts = source_part.split()
                        source_url_parts[0] = urljoin(base_url, source_url_parts[0])
                        source_fixed_parts.append(" ".join(source_url_parts))
                source["srcset"] = ", ".join(source_fixed_parts)

    # Convert backtick-wrapped text to <code> tags
    # Find all text nodes and replace `text` with <code>text</code>
    backtick_pattern = re.compile(r"`([^`]+)`")

    def backtick_to_code(match: re.Match[str]) -> str:
        """Convert backtick-wrapped text to <code> tags, escaping HTML inside."""
        content = match.group(1)
        # Escape HTML special characters to preserve code-like content
        escaped = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f"<code>{escaped}</code>"

    # Collect text nodes first to avoid modifying during iteration
    text_nodes_to_process: list[tuple[object, str]] = []
    for text_node in soup.find_all(string=backtick_pattern):
        if text_node.parent and text_node.parent.name not in ["code", "pre", "script", "style"]:
            # text_node string has decoded entities, so we need to escape them
            text_str = str(text_node)
            # Escape non-backtick content first, then convert backticks
            # We need to escape any HTML that's NOT inside backticks
            parts: list[str] = []
            last_end = 0
            for match in backtick_pattern.finditer(text_str):
                # Escape text before the match
                before = text_str[last_end : match.start()]
                escaped_before = before.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                parts.append(escaped_before)
                # Add the code tag
                parts.append(backtick_to_code(match))
                last_end = match.end()
            # Escape remaining text
            remaining = text_str[last_end:]
            escaped_remaining = remaining.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            parts.append(escaped_remaining)
            new_html = "".join(parts)

            if new_html != text_str:
                text_nodes_to_process.append((text_node, new_html))

    # Now process the collected nodes
    for text_node, new_html in text_nodes_to_process:
        # Parse the new HTML fragment without adding wrapper tags
        fragment = BeautifulSoup(new_html, "html.parser")
        # Replace the text node with all children from the fragment
        text_node.replace_with(fragment)  # type: ignore[arg-type]

    return str(soup)


def extract_fulltext(html: str, url: str | None = None) -> str | None:
    """
    Extract main content from HTML using Mozilla's Readability algorithm.

    Args:
        html: Raw HTML content.
        url: Optional URL for better extraction context.

    Returns:
        Extracted HTML content or None if extraction fails.
    """
    try:
        doc = Document(html, url=url)
        content = cast(str, doc.summary())
        # Return None if content is too short (likely extraction failure)
        if content and len(content) > 100:
            # Post-process to fix URLs and formatting
            return postprocess_html(content, base_url=url)
        return None
    except Exception:
        return None


async def fetch_and_extract_fulltext(url: str) -> str | None:
    """
    Fetch a URL and extract its main content.

    Args:
        url: URL to fetch and extract content from.

    Returns:
        Extracted HTML content or None if fetch/extraction fails.
    """
    async with httpx.AsyncClient(
        timeout=30.0,
        headers={"User-Agent": "Mozilla/5.0 (compatible; GleanBot/1.0)"},
        follow_redirects=True,
    ) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            return extract_fulltext(response.text, url=url)
        except Exception:
            return None

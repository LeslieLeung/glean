"""
Full-text content extractor.

Uses readability-lxml (Mozilla's Readability algorithm) to extract main content from web pages.
"""

import asyncio
from typing import cast
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag
from readability import Document

# Minimum content length threshold for successful extraction.
# 100 characters is chosen as a reasonable minimum to avoid storing
# snippets from failed extractions while still capturing short-form content.
MIN_CONTENT_LENGTH = 100


def _is_relative_url(url: str) -> bool:
    """Check if a URL is relative."""
    parsed = urlparse(url)
    return not parsed.scheme and not parsed.netloc


def _convert_backticks_to_code(soup: BeautifulSoup) -> None:
    """
    Convert backtick-wrapped text to <code> tags using proper HTML parsing.

    This function finds all text nodes containing backticks and converts them
    to alternating text and <code> elements. BeautifulSoup handles HTML entity
    escaping automatically when setting tag.string.

    Args:
        soup: BeautifulSoup object to process in-place.
    """
    # Find all text nodes (NavigableString) in the document
    # Collect them first to avoid modifying during iteration
    text_nodes = list(soup.find_all(string=True))

    for element in text_nodes:
        # Skip if parent is already code/pre/script/style
        if element.parent and element.parent.name in ["code", "pre", "script", "style"]:
            continue

        text = str(element)
        if "`" not in text:
            continue

        # Split on backticks and create alternating text/<code> nodes
        parts = text.split("`")
        if len(parts) <= 1:
            continue

        # Create fragment with alternating text and <code> elements
        fragment: list[NavigableString | Tag] = []
        for i, part in enumerate(parts):
            if i % 2 == 0:
                # Even indices: plain text
                if part:
                    fragment.append(NavigableString(part))
            else:
                # Odd indices: code content
                # BeautifulSoup automatically escapes HTML entities when setting .string
                code_tag = soup.new_tag("code")
                code_tag.string = part
                fragment.append(code_tag)

        # Replace original text node with fragment
        if fragment:
            element.replace_with(*fragment)


async def postprocess_html(html: str, base_url: str | None = None) -> str:
    """
    Post-process extracted HTML to fix common issues.

    - Converts relative URLs to absolute URLs for images and links
    - Converts backtick-wrapped text to <code> tags

    Runs CPU-intensive BeautifulSoup parsing in a thread pool to avoid
    blocking the event loop.

    Args:
        html: Extracted HTML content.
        base_url: Base URL for resolving relative paths.

    Returns:
        Processed HTML content.
    """
    # Parse HTML in thread pool (CPU-intensive operation)
    soup = await asyncio.to_thread(BeautifulSoup, html, "html.parser")

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

    # Convert backtick-wrapped text to <code> tags using proper HTML parsing
    _convert_backticks_to_code(soup)

    # Convert back to string in thread pool
    return await asyncio.to_thread(str, soup)


async def extract_fulltext(html: str, url: str | None = None) -> str | None:
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
        if content and len(content) > MIN_CONTENT_LENGTH:
            # Post-process to fix URLs and formatting
            return await postprocess_html(content, base_url=url)
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
            return await extract_fulltext(response.text, url=url)
        except Exception:
            return None

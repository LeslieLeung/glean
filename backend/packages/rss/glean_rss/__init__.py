"""
RSS processing package.

Provides RSS/Atom parsing, feed discovery, and OPML import/export.
"""

from .discoverer import discover_feed, fetch_feed
from .extractor import extract_fulltext, fetch_and_extract_fulltext, postprocess_html
from .opml import OPMLFeed, OPMLParseResult, generate_opml, parse_opml, parse_opml_with_folders
from .parser import ParsedEntry, ParsedFeed, parse_feed
from .safe_http import (
    DEFAULT_MAX_RESPONSE_BYTES,
    InvalidContentTypeError,
    ResponseTooLargeError,
    SSRFBlockedError,
    SSRFPolicy,
    safe_async_client,
    safe_fetch_bytes,
)
from .sanitizer import sanitize_html, sanitize_url
from .utils import strip_html_tags

__all__ = [
    "parse_feed",
    "ParsedFeed",
    "ParsedEntry",
    "discover_feed",
    "fetch_feed",
    "extract_fulltext",
    "fetch_and_extract_fulltext",
    "postprocess_html",
    "parse_opml",
    "parse_opml_with_folders",
    "generate_opml",
    "OPMLFeed",
    "OPMLParseResult",
    "strip_html_tags",
    "sanitize_html",
    "sanitize_url",
    "safe_async_client",
    "safe_fetch_bytes",
    "DEFAULT_MAX_RESPONSE_BYTES",
    "SSRFPolicy",
    "SSRFBlockedError",
    "ResponseTooLargeError",
    "InvalidContentTypeError",
]

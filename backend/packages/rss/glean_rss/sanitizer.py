"""
HTML and URL sanitization utilities for untrusted feed and webpage content.

Removes active HTML/scripting vectors, hidden comments, inline event handlers,
and unsafe URI schemes before storing or returning content across API/MCP/Admin.
"""

import re
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Comment, Doctype, ProcessingInstruction

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]+")
_EVENT_HANDLER_ATTR_RE = re.compile(r"^on", re.IGNORECASE)
_SAFE_DATA_IMAGE_RE = re.compile(
    r"^data:image/(?:png|jpeg|jpg|gif|webp|avif);base64,[A-Za-z0-9+/=\s]+$",
    re.IGNORECASE,
)
_SAFE_SOURCE_IMAGE_MIME_RE = re.compile(
    r"^image/(?:png|jpeg|jpg|gif|webp|avif)$",
    re.IGNORECASE,
)

# Tags whose entire subtree must be removed.
_DROP_SUBTREE_TAGS: frozenset[str] = frozenset(
    {
        "script",
        "style",
        "iframe",
        "object",
        "embed",
        "svg",
        "math",
        "form",
        "input",
        "button",
        "textarea",
        "select",
        "option",
        "optgroup",
        "fieldset",
        "noscript",
        "template",
        "meta",
        "link",
        "base",
        "applet",
        "frame",
        "frameset",
        "audio",
        "video",
    }
)

# Allowlisted article/reading tags. Unknown tags are unwrapped (text kept).
_ALLOWED_TAGS: frozenset[str] = frozenset(
    {
        "p",
        "br",
        "div",
        "span",
        "a",
        "img",
        "strong",
        "em",
        "b",
        "i",
        "u",
        "s",
        "code",
        "pre",
        "blockquote",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "ul",
        "ol",
        "li",
        "table",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "th",
        "td",
        "caption",
        "colgroup",
        "col",
        "hr",
        "figure",
        "figcaption",
        "picture",
        "source",
        "sub",
        "sup",
        "mark",
        "small",
        "dl",
        "dt",
        "dd",
        "abbr",
        "cite",
        "del",
        "ins",
        "time",
    }
)

_GLOBAL_ALLOWED_ATTRS: frozenset[str] = frozenset({"class", "id", "title", "dir", "lang"})
_TAG_ALLOWED_ATTRS: dict[str, frozenset[str]] = {
    "a": frozenset({"href", "rel", "target"}),
    "img": frozenset(
        {"src", "alt", "width", "height", "srcset", "sizes", "loading", "decoding", "data-src"}
    ),
    "source": frozenset({"srcset", "sizes", "media", "type"}),
    "th": frozenset({"colspan", "rowspan", "scope"}),
    "td": frozenset({"colspan", "rowspan"}),
    "time": frozenset({"datetime"}),
}


def sanitize_url(
    url: str | None,
    *,
    allow_mailto: bool = False,
    allow_data_image: bool = False,
    allow_relative: bool = False,
) -> str | None:
    """
    Validate and normalize an untrusted URL.

    Allows only http(s) URLs by default, plus optional mailto, safe raster
    base64 data:image/* URIs, or safe same-site relative paths.
    """
    if not url:
        return None

    cleaned = _CONTROL_CHAR_RE.sub("", url).strip()
    if not cleaned:
        return None

    if allow_data_image and cleaned.lower().startswith("data:"):
        if _SAFE_DATA_IMAGE_RE.match(cleaned):
            return cleaned
        return None

    try:
        parsed = urlparse(cleaned)
    except ValueError:
        return None

    scheme = parsed.scheme.lower()
    if not scheme:
        if allow_relative and not parsed.netloc and not cleaned.startswith("//"):
            return cleaned
        return None

    if scheme in {"http", "https"}:
        if not parsed.netloc:
            return None
        return cleaned

    if allow_mailto and scheme == "mailto":
        if parsed.path or "@" in cleaned:
            return cleaned
        return None

    return None


def _sanitize_srcset(srcset: str, *, allow_relative: bool = True) -> str | None:
    """Validate every candidate URL inside an img/source srcset attribute."""
    safe_candidates: list[str] = []
    for candidate in srcset.split(","):
        stripped = candidate.strip()
        if not stripped:
            continue
        parts = stripped.split(None, 1)
        safe_url = sanitize_url(parts[0], allow_data_image=True, allow_relative=allow_relative)
        if not safe_url:
            continue
        if len(parts) == 2:
            descriptor = parts[1].strip()
            if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?[wx]", descriptor):
                safe_candidates.append(f"{safe_url} {descriptor}")
        else:
            safe_candidates.append(safe_url)
    return ", ".join(safe_candidates) if safe_candidates else None


def sanitize_html(html_content: str | None) -> str | None:
    """
    Sanitize untrusted HTML using a strict tag/attribute/URL allowlist.

    Strips scripts, styles, iframes, SVGs, forms, HTML comments, event handlers,
    and dangerous URL schemes while preserving clean article reading markup.
    """
    if html_content is None:
        return None
    if not html_content:
        return ""

    soup = BeautifulSoup(html_content, "html.parser")

    # Remove comments, processing instructions, and doctype declarations.
    for node in list(soup.find_all(string=True)):
        if isinstance(node, (Comment, ProcessingInstruction, Doctype)):
            node.extract()

    # Drop dangerous elements and their subtrees first.
    for tag in list(soup.find_all(True)):
        if tag.parent is None:
            continue
        name = tag.name.lower()
        if name in _DROP_SUBTREE_TAGS:
            tag.decompose()

    # Walk remaining tags: unwrap disallowed benign tags, scrub attributes on allowed tags.
    for tag in list(soup.find_all(True)):
        if tag.parent is None:
            continue
        name = tag.name.lower()
        if name not in _ALLOWED_TAGS:
            tag.unwrap()
            continue

        allowed_attrs = _GLOBAL_ALLOWED_ATTRS | _TAG_ALLOWED_ATTRS.get(name, frozenset())
        new_attrs: dict[str, Any] = {}
        for attr_name, raw_value in list(tag.attrs.items()):
            attr_lower = attr_name.lower()
            if _EVENT_HANDLER_ATTR_RE.match(attr_lower):
                continue
            if attr_lower not in allowed_attrs:
                continue

            if isinstance(raw_value, list):
                value = " ".join(str(item) for item in raw_value)
            else:
                value = str(raw_value)

            if attr_lower == "href":
                safe_href = sanitize_url(value, allow_mailto=True, allow_relative=True)
                if not safe_href:
                    continue
                new_attrs["href"] = safe_href
            elif attr_lower in {"src", "data-src"}:
                safe_src = sanitize_url(value, allow_data_image=True, allow_relative=True)
                if not safe_src:
                    continue
                new_attrs[attr_lower] = safe_src
            elif attr_lower == "srcset":
                safe_srcset = _sanitize_srcset(value, allow_relative=True)
                if not safe_srcset:
                    continue
                new_attrs["srcset"] = safe_srcset
            elif name == "source" and attr_lower == "type":
                mime = value.split(";", 1)[0].strip()
                if not _SAFE_SOURCE_IMAGE_MIME_RE.match(mime):
                    continue
                new_attrs["type"] = mime
            elif attr_lower in {"width", "height", "colspan", "rowspan"}:
                cleaned_dim = value.strip()
                if re.fullmatch(r"[0-9]{1,5}(?:%|px)?", cleaned_dim):
                    new_attrs[attr_lower] = cleaned_dim
            elif attr_lower == "loading":
                if value.strip().lower() in {"lazy", "eager"}:
                    new_attrs["loading"] = value.strip().lower()
            elif attr_lower == "decoding":
                if value.strip().lower() in {"sync", "async", "auto"}:
                    new_attrs["decoding"] = value.strip().lower()
            elif attr_lower == "target":
                if value.strip().lower() == "_blank":
                    new_attrs["target"] = "_blank"
            elif attr_lower == "rel":
                continue
            else:
                new_attrs[attr_lower] = value

        if name == "a" and "href" in new_attrs:
            new_attrs["rel"] = "noopener noreferrer"

        tag.attrs.clear()
        tag.attrs.update(new_attrs)

    return str(soup)

"""
API router modules.

This package contains all API route handlers organized by domain.
"""

from . import (
    admin,
    api_tokens,
    auth,
    bookmarks,
    entries,
    extension,
    feeds,
    folders,
    preference,
    system,
    tags,
)

__all__ = [
    "auth",
    "feeds",
    "entries",
    "admin",
    # M2 routers
    "folders",
    "tags",
    "bookmarks",
    # M3 routers
    "preference",
    "system",
    "api_tokens",
    "extension",
]

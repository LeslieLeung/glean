"""
API router modules.

This package contains all API route handlers organized by domain.
"""

from . import admin, auth, bookmarks, entries, feeds, folders, preference, system, tags

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
]

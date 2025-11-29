"""
API router modules.

This package contains all API route handlers organized by domain.
"""

from . import admin, auth, entries, feeds

__all__ = ["auth", "feeds", "entries", "admin"]

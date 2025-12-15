"""
Database models package.

This module exports all SQLAlchemy models for the Glean application.
"""

from .admin import AdminRole, AdminUser, SystemConfig
from .base import Base, TimestampMixin
from .bookmark import Bookmark
from .entry import Entry
from .feed import Feed, FeedStatus
from .folder import Folder, FolderType
from .junction import BookmarkFolder, BookmarkTag, UserEntryTag
from .subscription import Subscription
from .tag import Tag
from .user import User
from .user_entry import UserEntry
from .user_preference_stats import UserPreferenceStats

__all__ = [
    "Base",
    "TimestampMixin",
    "User",
    "Feed",
    "FeedStatus",
    "Entry",
    "Subscription",
    "UserEntry",
    "AdminUser",
    "AdminRole",
    "SystemConfig",
    # M2 models
    "Folder",
    "FolderType",
    "Tag",
    "Bookmark",
    "BookmarkFolder",
    "BookmarkTag",
    "UserEntryTag",
    # M3 models
    "UserPreferenceStats",
]

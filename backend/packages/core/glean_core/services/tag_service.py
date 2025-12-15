"""
Tag service.

Handles tag CRUD operations and batch tagging.
"""

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core.schemas.tag import (
    TagCreate,
    TagListResponse,
    TagResponse,
    TagUpdate,
    TagWithCountsResponse,
)
from glean_database.models import BookmarkTag, Tag, UserEntryTag


class TagService:
    """Tag management service."""

    def __init__(self, session: AsyncSession):
        """
        Initialize tag service.

        Args:
            session: Database session.
        """
        self.session = session

    async def get_tags(self, user_id: str) -> TagListResponse:
        """
        Get all tags for a user with usage counts.

        Args:
            user_id: User identifier.

        Returns:
            Tag list response with counts.
        """
        stmt = select(Tag).where(Tag.user_id == user_id).order_by(Tag.name)
        result = await self.session.execute(stmt)
        tags = result.scalars().all()

        # Get counts for each tag
        tag_responses: list[TagWithCountsResponse] = []
        for tag in tags:
            # Count bookmarks with this tag
            bookmark_count_stmt = (
                select(func.count()).select_from(BookmarkTag).where(BookmarkTag.tag_id == tag.id)
            )
            bookmark_result = await self.session.execute(bookmark_count_stmt)
            bookmark_count = bookmark_result.scalar_one()

            # Count entries with this tag
            entry_count_stmt = (
                select(func.count()).select_from(UserEntryTag).where(UserEntryTag.tag_id == tag.id)
            )
            entry_result = await self.session.execute(entry_count_stmt)
            entry_count = entry_result.scalar_one()

            tag_responses.append(
                TagWithCountsResponse(
                    id=tag.id,
                    user_id=tag.user_id,
                    name=tag.name,
                    color=tag.color,
                    created_at=tag.created_at,
                    bookmark_count=bookmark_count,
                    entry_count=entry_count,
                )
            )

        return TagListResponse(tags=tag_responses)

    async def get_tag(self, tag_id: str, user_id: str) -> TagResponse:
        """
        Get a specific tag.

        Args:
            tag_id: Tag identifier.
            user_id: User identifier for authorization.

        Returns:
            Tag response.

        Raises:
            ValueError: If tag not found or unauthorized.
        """
        stmt = select(Tag).where(Tag.id == tag_id, Tag.user_id == user_id)
        result = await self.session.execute(stmt)
        tag = result.scalar_one_or_none()

        if not tag:
            raise ValueError("Tag not found")

        return TagResponse.model_validate(tag)

    async def create_tag(self, user_id: str, data: TagCreate) -> TagResponse:
        """
        Create a new tag.

        Args:
            user_id: User identifier.
            data: Tag creation data.

        Returns:
            Created tag response.

        Raises:
            ValueError: If tag name already exists for user.
        """
        # Check for duplicate name
        existing_stmt = select(Tag).where(Tag.user_id == user_id, Tag.name == data.name)
        result = await self.session.execute(existing_stmt)
        if result.scalar_one_or_none():
            raise ValueError("Tag with this name already exists")

        tag = Tag(
            user_id=user_id,
            name=data.name,
            color=data.color,
        )
        self.session.add(tag)
        await self.session.commit()
        await self.session.refresh(tag)

        return TagResponse.model_validate(tag)

    async def update_tag(self, tag_id: str, user_id: str, data: TagUpdate) -> TagResponse:
        """
        Update a tag.

        Args:
            tag_id: Tag identifier.
            user_id: User identifier for authorization.
            data: Update data.

        Returns:
            Updated tag response.

        Raises:
            ValueError: If tag not found, unauthorized, or name already exists.
        """
        tag = await self._get_tag_or_raise(tag_id, user_id)

        if data.name is not None:
            # Check for duplicate name
            existing_stmt = select(Tag).where(
                Tag.user_id == user_id, Tag.name == data.name, Tag.id != tag_id
            )
            result = await self.session.execute(existing_stmt)
            if result.scalar_one_or_none():
                raise ValueError("Tag with this name already exists")
            tag.name = data.name

        if data.color is not None:
            tag.color = data.color

        await self.session.commit()
        await self.session.refresh(tag)

        return TagResponse.model_validate(tag)

    async def delete_tag(self, tag_id: str, user_id: str) -> None:
        """
        Delete a tag.

        Associated bookmark_tags and user_entry_tags are cascade deleted.

        Args:
            tag_id: Tag identifier.
            user_id: User identifier for authorization.

        Raises:
            ValueError: If tag not found or unauthorized.
        """
        tag = await self._get_tag_or_raise(tag_id, user_id)
        await self.session.delete(tag)
        await self.session.commit()

    async def batch_add_tag(
        self,
        tag_id: str,
        user_id: str,
        target_type: str,
        target_ids: list[str],
    ) -> int:
        """
        Add a tag to multiple targets.

        Args:
            tag_id: Tag identifier.
            user_id: User identifier for authorization.
            target_type: Type of target (bookmark or user_entry).
            target_ids: List of target identifiers.

        Returns:
            Number of tags added.

        Raises:
            ValueError: If tag not found or invalid target type.
        """
        # Verify tag exists and belongs to user
        await self._get_tag_or_raise(tag_id, user_id)

        added = 0
        if target_type == "bookmark":
            for target_id in target_ids:
                # Check if already exists
                existing = await self.session.execute(
                    select(BookmarkTag).where(
                        BookmarkTag.bookmark_id == target_id,
                        BookmarkTag.tag_id == tag_id,
                    )
                )
                if not existing.scalar_one_or_none():
                    self.session.add(BookmarkTag(bookmark_id=target_id, tag_id=tag_id))
                    added += 1
        elif target_type == "user_entry":
            for target_id in target_ids:
                # Check if already exists
                existing = await self.session.execute(
                    select(UserEntryTag).where(
                        UserEntryTag.user_entry_id == target_id,
                        UserEntryTag.tag_id == tag_id,
                    )
                )
                if not existing.scalar_one_or_none():
                    self.session.add(UserEntryTag(user_entry_id=target_id, tag_id=tag_id))
                    added += 1
        else:
            raise ValueError(f"Invalid target type: {target_type}")

        await self.session.commit()
        return added

    async def batch_remove_tag(
        self,
        tag_id: str,
        user_id: str,
        target_type: str,
        target_ids: list[str],
    ) -> int:
        """
        Remove a tag from multiple targets.

        Args:
            tag_id: Tag identifier.
            user_id: User identifier for authorization.
            target_type: Type of target (bookmark or user_entry).
            target_ids: List of target identifiers.

        Returns:
            Number of tags removed.

        Raises:
            ValueError: If tag not found or invalid target type.
        """
        # Verify tag exists and belongs to user
        await self._get_tag_or_raise(tag_id, user_id)

        if target_type == "bookmark":
            stmt = delete(BookmarkTag).where(
                BookmarkTag.bookmark_id.in_(target_ids),
                BookmarkTag.tag_id == tag_id,
            )
        elif target_type == "user_entry":
            stmt = delete(UserEntryTag).where(
                UserEntryTag.user_entry_id.in_(target_ids),
                UserEntryTag.tag_id == tag_id,
            )
        else:
            raise ValueError(f"Invalid target type: {target_type}")

        result: CursorResult[Any] = await self.session.execute(stmt)  # type: ignore[assignment]
        await self.session.commit()
        return result.rowcount or 0

    async def _get_tag_or_raise(self, tag_id: str, user_id: str) -> Tag:
        """Get a tag by ID or raise ValueError."""
        stmt = select(Tag).where(Tag.id == tag_id, Tag.user_id == user_id)
        result = await self.session.execute(stmt)
        tag = result.scalar_one_or_none()
        if not tag:
            raise ValueError("Tag not found")
        return tag

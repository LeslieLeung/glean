"""
Admin service.

Provides business logic for administrative operations.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from glean_database.models.admin import AdminRole, AdminUser
from glean_database.models.entry import Entry
from glean_database.models.feed import Feed, FeedStatus
from glean_database.models.subscription import Subscription
from glean_database.models.user import User

from ..auth.password import hash_password, verify_password
from .system_config_service import SystemConfigService


class AdminService:
    """Service for administrative operations."""

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize admin service.

        Args:
            session: Database session.
        """
        self.session = session
        self.system_config = SystemConfigService(session)

    async def authenticate_admin(self, username: str, password: str) -> AdminUser | None:
        """
        Authenticate admin user.

        Args:
            username: Admin username.
            password: Plain text password.

        Returns:
            AdminUser if successful, None otherwise.
        """
        result = await self.session.execute(
            select(AdminUser).where(AdminUser.username == username, AdminUser.is_active.is_(True))
        )
        admin = result.scalar_one_or_none()

        if not admin or not verify_password(password, admin.password_hash):
            return None

        # Update last login time
        admin.last_login_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(admin)

        return admin

    async def create_admin_user(
        self, username: str, password: str, role: AdminRole = AdminRole.ADMIN
    ) -> AdminUser:
        """
        Create a new admin user.

        Args:
            username: Admin username.
            password: Plain text password.
            role: Admin role.

        Returns:
            Created admin user.
        """
        admin = AdminUser(
            username=username, password_hash=hash_password(password), role=role, is_active=True
        )
        self.session.add(admin)
        await self.session.commit()
        await self.session.refresh(admin)
        return admin

    async def get_admin_by_id(self, admin_id: str) -> AdminUser | None:
        """
        Get admin user by ID.

        Args:
            admin_id: Admin user ID.

        Returns:
            Admin user if found, None otherwise.
        """
        result = await self.session.execute(select(AdminUser).where(AdminUser.id == admin_id))
        return result.scalar_one_or_none()

    async def list_users(
        self, page: int = 1, per_page: int = 20, search: str | None = None
    ) -> tuple[list[User], int]:
        """
        List all users with pagination.

        Args:
            page: Page number (1-based).
            per_page: Items per page.
            search: Search query (email or username).

        Returns:
            Tuple of (users list, total count).
        """
        # Build query
        query = select(User)
        count_query = select(func.count()).select_from(User)

        if search:
            search_filter = User.email.ilike(f"%{search}%")
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        # Get total count
        result = await self.session.execute(count_query)
        total = result.scalar_one()

        # Get paginated results
        query = query.order_by(User.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
        result = await self.session.execute(query)
        users = list(result.scalars().all())

        return users, total

    async def toggle_user_status(self, user_id: str, is_active: bool) -> User | None:
        """
        Enable or disable a user account.

        Args:
            user_id: User ID.
            is_active: Target active status.

        Returns:
            Updated user if found, None otherwise.
        """
        result = await self.session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return None

        user.is_active = is_active
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def get_dashboard_stats(self) -> dict[str, int]:
        """
        Get dashboard statistics.

        Returns:
            Dictionary containing various system statistics.
        """
        # Total users
        total_users_result = await self.session.execute(select(func.count()).select_from(User))
        total_users = total_users_result.scalar_one()

        # Active users (last 7 days)
        seven_days_ago = (datetime.now(UTC) - timedelta(days=7)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        active_users_result = await self.session.execute(
            select(func.count()).select_from(User).where(User.last_login_at >= seven_days_ago)
        )
        active_users = active_users_result.scalar_one()

        # Total feeds
        total_feeds_result = await self.session.execute(select(func.count()).select_from(Feed))
        total_feeds = total_feeds_result.scalar_one()

        # Total entries
        total_entries_result = await self.session.execute(select(func.count()).select_from(Entry))
        total_entries = total_entries_result.scalar_one()

        # Total subscriptions
        total_subs_result = await self.session.execute(
            select(func.count()).select_from(Subscription)
        )
        total_subscriptions = total_subs_result.scalar_one()

        # New users today
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        new_users_result = await self.session.execute(
            select(func.count()).select_from(User).where(User.created_at >= today)
        )
        new_users_today = new_users_result.scalar_one()

        # New entries today
        new_entries_result = await self.session.execute(
            select(func.count()).select_from(Entry).where(Entry.created_at >= today)
        )
        new_entries_today = new_entries_result.scalar_one()

        return {
            "total_users": total_users,
            "active_users": active_users,
            "total_feeds": total_feeds,
            "total_entries": total_entries,
            "total_subscriptions": total_subscriptions,
            "new_users_today": new_users_today,
            "new_entries_today": new_entries_today,
        }

    # M2: Feed management methods
    async def list_feeds(
        self,
        page: int = 1,
        per_page: int = 20,
        status: str | None = None,
        search: str | None = None,
        sort: str = "created_at",
        order: str = "desc",
    ) -> tuple[list[dict[str, Any]], int]:
        """
        List all feeds with pagination and filtering.

        Args:
            page: Page number (1-based).
            per_page: Items per page.
            status: Filter by status.
            search: Search in title or URL.
            sort: Sort field.
            order: Sort order.

        Returns:
            Tuple of (feed list with subscriber counts, total count).
        """
        # Build base query
        query = select(Feed)
        count_query = select(func.count()).select_from(Feed)

        # Apply filters
        if status:
            query = query.where(Feed.status == status)
            count_query = count_query.where(Feed.status == status)

        if search:
            search_filter = Feed.title.ilike(f"%{search}%") | Feed.url.ilike(f"%{search}%")
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        # Get total count
        result = await self.session.execute(count_query)
        total = result.scalar_one()

        # Apply sorting
        sort_column = getattr(Feed, sort, Feed.created_at)
        if order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # Apply pagination
        query = query.offset((page - 1) * per_page).limit(per_page)

        result = await self.session.execute(query)
        feeds = list(result.scalars().all())

        # Get subscriber counts for each feed
        feed_data = []
        for feed in feeds:
            sub_count_result = await self.session.execute(
                select(func.count())
                .select_from(Subscription)
                .where(Subscription.feed_id == feed.id)
            )
            subscriber_count = sub_count_result.scalar_one()

            feed_data.append(
                {
                    "id": feed.id,
                    "url": feed.url,
                    "title": feed.title,
                    "status": feed.status,
                    "subscriber_count": subscriber_count,
                    "last_fetched_at": feed.last_fetched_at,
                    "error_count": feed.error_count,
                    "fetch_error_message": feed.fetch_error_message,
                    "created_at": feed.created_at,
                }
            )

        return feed_data, total

    async def get_feed(self, feed_id: str) -> dict[str, Any] | None:
        """
        Get feed details by ID.

        Args:
            feed_id: Feed identifier.

        Returns:
            Feed details or None if not found.
        """
        result = await self.session.execute(select(Feed).where(Feed.id == feed_id))
        feed = result.scalar_one_or_none()

        if not feed:
            return None

        # Get subscriber count
        sub_count_result = await self.session.execute(
            select(func.count()).select_from(Subscription).where(Subscription.feed_id == feed.id)
        )
        subscriber_count = sub_count_result.scalar_one()

        return {
            "id": feed.id,
            "url": feed.url,
            "title": feed.title,
            "description": feed.description,
            "icon_url": feed.icon_url,
            "status": feed.status,
            "subscriber_count": subscriber_count,
            "last_fetched_at": feed.last_fetched_at,
            "error_count": feed.error_count,
            "last_error_message": feed.fetch_error_message,
            "created_at": feed.created_at,
        }

    async def update_feed(
        self,
        feed_id: str,
        url: str | None = None,
        title: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Update a feed.

        Args:
            feed_id: Feed identifier.
            url: New URL.
            title: New title.
            status: New status.

        Returns:
            Updated feed or None if not found.
        """
        result = await self.session.execute(select(Feed).where(Feed.id == feed_id))
        feed = result.scalar_one_or_none()

        if not feed:
            return None

        if url is not None:
            feed.url = url
        if title is not None:
            feed.title = title
        if status is not None:
            feed.status = FeedStatus(status)

        await self.session.commit()
        await self.session.refresh(feed)

        return await self.get_feed(feed_id)

    async def reset_feed_error(self, feed_id: str) -> dict[str, Any] | None:
        """
        Reset error count for a feed.

        Args:
            feed_id: Feed identifier.

        Returns:
            Updated feed or None if not found.
        """
        result = await self.session.execute(select(Feed).where(Feed.id == feed_id))
        feed = result.scalar_one_or_none()

        if not feed:
            return None

        feed.error_count = 0
        feed.fetch_error_message = None
        feed.status = FeedStatus.ACTIVE

        await self.session.commit()
        await self.session.refresh(feed)

        return await self.get_feed(feed_id)

    async def delete_feed(self, feed_id: str) -> bool:
        """
        Delete a feed and all related data.

        Args:
            feed_id: Feed identifier.

        Returns:
            True if deleted, False if not found.
        """
        result = await self.session.execute(select(Feed).where(Feed.id == feed_id))
        feed = result.scalar_one_or_none()

        if not feed:
            return False

        await self.session.delete(feed)
        await self.session.commit()
        return True

    async def batch_feed_operation(self, action: str, feed_ids: list[str]) -> int:
        """
        Perform batch operation on feeds.

        Args:
            action: Action to perform (enable, disable, delete).
            feed_ids: List of feed IDs.

        Returns:
            Number of affected feeds.
        """
        result = await self.session.execute(select(Feed).where(Feed.id.in_(feed_ids)))
        feeds = list(result.scalars().all())

        count = 0
        for feed in feeds:
            if action == "enable":
                feed.status = FeedStatus.ACTIVE
                count += 1
            elif action == "disable":
                feed.status = FeedStatus.DISABLED
                count += 1
            elif action == "delete":
                await self.session.delete(feed)
                count += 1

        await self.session.commit()
        return count

    # M2: Entry management methods
    async def list_entries(
        self,
        page: int = 1,
        per_page: int = 20,
        feed_id: str | None = None,
        search: str | None = None,
        sort: str = "created_at",
        order: str = "desc",
    ) -> tuple[list[dict[str, Any]], int]:
        """
        List all entries with pagination and filtering.

        Args:
            page: Page number (1-based).
            per_page: Items per page.
            feed_id: Filter by feed.
            search: Search in title.
            sort: Sort field.
            order: Sort order.

        Returns:
            Tuple of (entry list, total count).
        """
        # Build base query
        query = select(Entry, Feed.title.label("feed_title")).join(Feed, Entry.feed_id == Feed.id)
        count_query = select(func.count()).select_from(Entry)

        # Apply filters
        if feed_id:
            query = query.where(Entry.feed_id == feed_id)
            count_query = count_query.where(Entry.feed_id == feed_id)

        if search:
            query = query.where(Entry.title.ilike(f"%{search}%"))
            count_query = count_query.where(Entry.title.ilike(f"%{search}%"))

        # Get total count
        result = await self.session.execute(count_query)
        total = result.scalar_one()

        # Apply sorting
        sort_column = getattr(Entry, sort, Entry.created_at)
        if order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # Apply pagination
        query = query.offset((page - 1) * per_page).limit(per_page)

        result = await self.session.execute(query)
        rows = result.all()

        entries = [
            {
                "id": row.Entry.id,
                "feed_id": row.Entry.feed_id,
                "feed_title": row.feed_title,
                "url": row.Entry.url,
                "title": row.Entry.title,
                "author": row.Entry.author,
                "published_at": row.Entry.published_at,
                "created_at": row.Entry.created_at,
            }
            for row in rows
        ]

        return entries, total

    async def get_entry(self, entry_id: str) -> dict[str, Any] | None:
        """
        Get entry details by ID.

        Args:
            entry_id: Entry identifier.

        Returns:
            Entry details or None if not found.
        """
        result = await self.session.execute(
            select(Entry, Feed.title.label("feed_title"))
            .join(Feed, Entry.feed_id == Feed.id)
            .where(Entry.id == entry_id)
        )
        row = result.one_or_none()

        if not row:
            return None

        return {
            "id": row.Entry.id,
            "feed_id": row.Entry.feed_id,
            "feed_title": row.feed_title,
            "url": row.Entry.url,
            "title": row.Entry.title,
            "author": row.Entry.author,
            "content": row.Entry.content,
            "summary": row.Entry.summary,
            "published_at": row.Entry.published_at,
            "created_at": row.Entry.created_at,
        }

    async def delete_entry(self, entry_id: str) -> bool:
        """
        Delete an entry.

        Args:
            entry_id: Entry identifier.

        Returns:
            True if deleted, False if not found.
        """
        result = await self.session.execute(select(Entry).where(Entry.id == entry_id))
        entry = result.scalar_one_or_none()

        if not entry:
            return False

        await self.session.delete(entry)
        await self.session.commit()
        return True

    async def batch_entry_operation(self, action: str, entry_ids: list[str]) -> int:
        """
        Perform batch operation on entries.

        Args:
            action: Action to perform (delete).
            entry_ids: List of entry IDs.

        Returns:
            Number of affected entries.
        """
        if action != "delete":
            return 0

        result = await self.session.execute(select(Entry).where(Entry.id.in_(entry_ids)))
        entries = list(result.scalars().all())

        count = 0
        for entry in entries:
            await self.session.delete(entry)
            count += 1

        await self.session.commit()
        return count

    # =========================
    # System settings: embedding
    # =========================
    async def get_embedding_config(self) -> dict[str, Any] | None:
        """Return current embedding configuration from system settings."""
        return await self.system_config.get_config("embedding.config")

    async def save_embedding_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """
        Validate and persist embedding configuration.

        Adds version and updated_at for tracking.
        """
        provider = (config.get("provider") or "").lower()
        dimension = config.get("dimension")
        if not provider:
            raise ValueError("provider is required")
        if dimension is None:
            raise ValueError("dimension is required")
        if provider in ("volc-engine", "volc_engine", "volcengine") and not dimension:
            raise ValueError("VolcEngine requires explicit dimension")

        version = uuid4().hex
        now = datetime.now(UTC).isoformat()
        config["version"] = version
        config["updated_at"] = now

        await self.system_config.set_config(
            "embedding.config", config, description="Embedding provider config"
        )
        return config

    async def get_embedding_progress(self) -> dict[str, int]:
        """
        Compute embedding rebuild progress using entry counters.
        """
        total_result = await self.session.execute(select(func.count()).select_from(Entry))
        total = total_result.scalar_one()

        done_query = select(func.count()).select_from(Entry).where(Entry.embedding_status == "done")
        done_result = await self.session.execute(done_query)
        done = done_result.scalar_one()

        failed_query = (
            select(func.count()).select_from(Entry).where(Entry.embedding_status == "failed")
        )
        failed_result = await self.session.execute(failed_query)
        failed = failed_result.scalar_one()

        return {"total": total, "done": done, "failed": failed}

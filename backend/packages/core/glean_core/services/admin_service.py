"""
Admin service.

Provides business logic for administrative operations.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from glean_database.models.admin import AdminRole, AdminUser
from glean_database.models.entry import Entry
from glean_database.models.feed import Feed
from glean_database.models.subscription import Subscription
from glean_database.models.user import User

from ..auth.password import hash_password, verify_password


class AdminService:
    """Service for administrative operations."""

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize admin service.

        Args:
            session: Database session.
        """
        self.session = session

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
        seven_days_ago = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        seven_days_ago = seven_days_ago.replace(day=seven_days_ago.day - 7)
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

"""
User service.

Handles user profile management and settings.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from glean_core.auth.password import hash_password_async
from glean_core.schemas import UserResponse, UserUpdate
from glean_core.schemas.user import UserCreate
from glean_database.models import User


class UserService:
    """User management service."""

    def __init__(self, session: AsyncSession):
        """
        Initialize user service.

        Args:
            session: Database session.
        """
        self.session = session

    async def create_user(self, user_create: UserCreate) -> User:
        """
        Create a new user.

        Args:
            user_create: User creation data.

        Returns:
            Created user instance.
        """
        user = User(
            email=user_create.email,
            name=user_create.name,
            password_hash=await hash_password_async(user_create.password),
            is_active=True,
            is_verified=False,
        )

        self.session.add(user)
        await self.session.flush()
        return user

    async def get_user(self, user_id: str) -> UserResponse:
        """
        Get user by ID.

        Args:
            user_id: User identifier.

        Returns:
            User response.

        Raises:
            ValueError: If user not found.
        """
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise ValueError("User not found")

        return UserResponse.model_validate(user)

    async def update_user(self, user_id: str, update: UserUpdate) -> UserResponse:
        """
        Update user profile.

        Args:
            user_id: User identifier.
            update: Update data.

        Returns:
            Updated user response.

        Raises:
            ValueError: If user not found.
        """
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise ValueError("User not found")

        # Update fields
        if update.name is not None:
            user.name = update.name
        if update.avatar_url is not None:
            user.avatar_url = update.avatar_url
        if update.settings is not None:
            user.settings = update.settings

        await self.session.commit()
        await self.session.refresh(user)

        return UserResponse.model_validate(user)

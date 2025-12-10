"""
System service.

Provides logic for system settings.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from glean_database.models.system_setting import SystemSetting


class SystemService:
    """Service for system settings."""

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize system service.

        Args:
            session: Database session.
        """
        self.session = session

    async def get_setting(self, key: str, default: str | None = None) -> str | None:
        """
        Get a system setting by key.

        Args:
            key: Setting key.
            default: Default value if not found.

        Returns:
            Setting value or default.
        """
        result = await self.session.execute(select(SystemSetting).where(SystemSetting.key == key))
        setting = result.scalar_one_or_none()
        return setting.value if setting else default

    async def set_setting(self, key: str, value: str, description: str | None = None) -> SystemSetting:
        """
        Set a system setting.

        Args:
            key: Setting key.
            value: Setting value.
            description: Optional description.

        Returns:
            Updated setting.
        """
        result = await self.session.execute(select(SystemSetting).where(SystemSetting.key == key))
        setting = result.scalar_one_or_none()

        if setting:
            setting.value = value
            if description:
                setting.description = description
        else:
            setting = SystemSetting(key=key, value=value, description=description)
            self.session.add(setting)

        await self.session.commit()
        await self.session.refresh(setting)
        return setting

    async def is_registration_enabled(self) -> bool:
        """
        Check if user registration is enabled.

        Returns:
            True if enabled, False otherwise.
        """
        value = await self.get_setting("registration_enabled", "true")
        return value.lower() == "true"

    async def set_registration_enabled(self, enabled: bool) -> SystemSetting:
        """
        Set registration enabled status.

        Args:
            enabled: True to enable, False to disable.

        Returns:
            Updated setting.
        """
        return await self.set_setting(
            "registration_enabled", "true" if enabled else "false", "Enable or disable user registration"
        )

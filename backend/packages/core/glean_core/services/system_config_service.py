"""
System configuration service.

Provides typed helpers around the SystemConfig key-value store.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from glean_database.models import SystemConfig


class SystemConfigService:
    """Service to read/write system-level configuration."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_config(self, key: str) -> dict[str, Any] | None:
        """Fetch config value by key."""
        result = await self.session.execute(select(SystemConfig).where(SystemConfig.key == key))
        row = result.scalar_one_or_none()
        return row.value if row else None

    async def set_config(
        self, key: str, value: dict[str, Any], description: str | None = None
    ) -> None:
        """Upsert config value."""
        result = await self.session.execute(select(SystemConfig).where(SystemConfig.key == key))
        existing = result.scalar_one_or_none()

        if existing:
            existing.value = value
            if description is not None:
                existing.description = description
        else:
            self.session.add(SystemConfig(key=key, value=value, description=description))

        await self.session.commit()

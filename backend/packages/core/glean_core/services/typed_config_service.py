"""
Typed configuration service.

Provides type-safe access to system configuration stored in the database.
Each config class carries its NAMESPACE for database storage key.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from glean_database.models import SystemConfig

if TYPE_CHECKING:
    pass

T = TypeVar("T", bound=BaseModel)


class TypedConfigService:
    """
    Type-safe configuration service.

    Provides get/update methods for typed configuration schemas.
    Configuration is stored as JSON in the system_configs table.

    Example:
        >>> service = TypedConfigService(session)
        >>> config = await service.get(EmbeddingConfig)
        >>> print(config.enabled)
        False
        >>> updated = await service.update(EmbeddingConfig, enabled=True)
    """

    def __init__(self, session: AsyncSession, allow_env_override: bool = False) -> None:
        """
        Initialize typed config service.

        Args:
            session: Database session.
            allow_env_override: If True, allows environment variables to override
                               database values. Only for testing purposes.
        """
        self.session = session
        self._allow_env = allow_env_override

    async def _get_from_db(self, namespace: str) -> dict[str, Any] | None:
        """Get raw config data from database."""
        result = await self.session.execute(
            select(SystemConfig).where(SystemConfig.key == namespace)
        )
        row = result.scalar_one_or_none()
        return row.value if row else None

    async def _set_to_db(self, namespace: str, value: dict[str, Any]) -> None:
        """Save config data to database."""
        result = await self.session.execute(
            select(SystemConfig).where(SystemConfig.key == namespace)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.value = value
        else:
            self.session.add(SystemConfig(key=namespace, value=value))

        await self.session.commit()

    def _get_from_env(self, namespace: str, config_class: type[T]) -> dict[str, Any]:
        """
        Get config values from environment variables.

        Environment variables are expected in the format:
        {NAMESPACE}_{FIELD} (uppercase), e.g., EMBEDDING_PROVIDER, EMBEDDING_API_KEY
        """
        env_data: dict[str, Any] = {}
        prefix = namespace.upper() + "_"

        # Get field names and types from the config class
        for field_name, field_info in config_class.model_fields.items():
            # Skip class variables (like NAMESPACE)
            if field_name == "NAMESPACE":
                continue

            env_key = prefix + field_name.upper()
            env_value = os.environ.get(env_key)

            if env_value is not None:
                # Convert string value to appropriate type
                field_type = field_info.annotation
                try:
                    origin = getattr(field_type, "__origin__", None)
                    if field_type is bool or origin is bool:
                        env_data[field_name] = env_value.lower() in ("true", "1", "yes")
                    elif field_type is int or origin is int:
                        env_data[field_name] = int(env_value)
                    elif field_type is float or origin is float:
                        env_data[field_name] = float(env_value)
                    else:
                        env_data[field_name] = env_value
                except (ValueError, TypeError):
                    # Skip invalid values
                    pass

        return env_data

    async def get(self, config_class: type[T]) -> T:
        """
        Get configuration with type safety.

        Args:
            config_class: The configuration class to retrieve.
                         Must have a NAMESPACE class variable.

        Returns:
            Configuration instance with values from database,
            falling back to schema defaults for missing fields.

        Example:
            >>> config = await service.get(EmbeddingConfig)
            >>> print(config.provider)
            'openai'
        """
        namespace = getattr(config_class, "NAMESPACE", None)
        if not namespace:
            raise ValueError(f"Config class {config_class.__name__} must have NAMESPACE")

        db_data = await self._get_from_db(namespace)

        if self._allow_env:
            # Test mode: allow env override
            env_data = self._get_from_env(namespace, config_class)
            merged = {**env_data, **(db_data or {})}
            return config_class(**merged)

        # Production mode: DB only, defaults from schema
        return config_class(**(db_data or {}))

    async def update(self, config_class: type[T], **updates: Any) -> T:
        """
        Partially update configuration.

        Args:
            config_class: The configuration class to update.
            **updates: Fields to update.

        Returns:
            Updated configuration instance.

        Example:
            >>> updated = await service.update(EmbeddingConfig, enabled=True, provider="openai")
        """
        namespace = getattr(config_class, "NAMESPACE", None)
        if not namespace:
            raise ValueError(f"Config class {config_class.__name__} must have NAMESPACE")

        # Get current config
        current = await self.get(config_class)

        # Apply updates
        updated = current.model_copy(update=updates)

        # Serialize and save
        # Use mode="json" for proper datetime serialization
        data = updated.model_dump(mode="json", exclude={"NAMESPACE"})
        await self._set_to_db(namespace, data)

        return updated

    async def set(self, config_class: type[T], config: T) -> T:
        """
        Set entire configuration.

        Args:
            config_class: The configuration class.
            config: The configuration instance to save.

        Returns:
            The saved configuration instance.
        """
        namespace = getattr(config_class, "NAMESPACE", None)
        if not namespace:
            raise ValueError(f"Config class {config_class.__name__} must have NAMESPACE")

        data = config.model_dump(mode="json", exclude={"NAMESPACE"})
        await self._set_to_db(namespace, data)
        return config

    async def delete(self, config_class: type[T]) -> None:
        """
        Delete configuration (reset to defaults).

        Args:
            config_class: The configuration class to delete.
        """
        namespace = getattr(config_class, "NAMESPACE", None)
        if not namespace:
            raise ValueError(f"Config class {config_class.__name__} must have NAMESPACE")

        result = await self.session.execute(
            select(SystemConfig).where(SystemConfig.key == namespace)
        )
        existing = result.scalar_one_or_none()

        if existing:
            await self.session.delete(existing)
            await self.session.commit()

    async def update_embedding_version(self) -> str:
        """
        Generate and set a new version for embedding config.

        Called when embedding config changes to trigger re-embedding.

        Returns:
            The new version UUID.
        """
        from glean_core.schemas.config import EmbeddingConfig

        new_version = str(uuid.uuid4())
        await self.update(EmbeddingConfig, version=new_version)
        return new_version

    async def set_embedding_status(
        self,
        status: str,
        error: str | None = None,
    ) -> None:
        """
        Update embedding system status.

        Args:
            status: New status value.
            error: Optional error message.
        """
        from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus

        updates: dict[str, Any] = {"status": VectorizationStatus(status)}

        if error:
            updates["last_error"] = error
            updates["last_error_at"] = datetime.now(UTC)
            # Increment error count
            current = await self.get(EmbeddingConfig)
            updates["error_count"] = current.error_count + 1
        elif status == VectorizationStatus.IDLE:
            # Clear error on successful state
            updates["last_error"] = None
            updates["error_count"] = 0

        await self.update(EmbeddingConfig, **updates)

    async def start_rebuild(self) -> str:
        """
        Mark rebuild as started and return rebuild ID.

        Returns:
            The rebuild ID.
        """
        from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus

        rebuild_id = str(uuid.uuid4())
        await self.update(
            EmbeddingConfig,
            status=VectorizationStatus.REBUILDING,
            rebuild_id=rebuild_id,
            rebuild_started_at=datetime.now(UTC),
        )
        return rebuild_id

    async def complete_rebuild(self) -> None:
        """Mark rebuild as completed."""
        from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus

        await self.update(
            EmbeddingConfig,
            status=VectorizationStatus.IDLE,
            rebuild_id=None,
            rebuild_started_at=None,
            error_count=0,
            last_error=None,
        )

    async def is_vectorization_enabled(self) -> bool:
        """
        Check if vectorization is enabled and operational.

        Returns:
            True if enabled and status is IDLE or REBUILDING.
        """
        from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus

        config = await self.get(EmbeddingConfig)
        return config.enabled and config.status in (
            VectorizationStatus.IDLE,
            VectorizationStatus.REBUILDING,
        )

    async def is_registration_enabled(self) -> bool:
        """
        Check if user registration is enabled.

        Returns:
            True if registration is enabled, False otherwise.
        """
        from glean_core.schemas.config import RegistrationConfig

        config = await self.get(RegistrationConfig)
        return config.enabled

    async def set_registration_enabled(self, enabled: bool) -> None:
        """
        Set registration enabled status.

        Args:
            enabled: True to enable registration, False to disable.
        """
        from glean_core.schemas.config import RegistrationConfig

        await self.update(RegistrationConfig, enabled=enabled)

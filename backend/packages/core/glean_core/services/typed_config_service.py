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
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from glean_database.models import SystemConfig

if TYPE_CHECKING:
    from glean_core.schemas.config import EmbeddingConfig

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

    async def _lock_namespace(self, namespace: str) -> None:
        """Serialize updates even before the first config row exists."""
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:namespace))"),
            {"namespace": f"glean:system_config:{namespace}"},
        )

    async def _get_from_db(self, namespace: str) -> dict[str, Any] | None:
        """Get raw config data from database."""
        result = await self.session.execute(
            select(SystemConfig).where(SystemConfig.key == namespace)
        )
        row = result.scalar_one_or_none()
        return row.value if row else None

    async def _set_to_db(self, namespace: str, value: dict[str, Any]) -> None:
        """Save config data to database."""
        await self._lock_namespace(namespace)
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

        # Serialize concurrent partial updates through the config row.  The
        # previous get-then-set implementation could lose a version/status
        # transition when an API request and a worker completed at the same
        # time because both rewrote the whole JSON document from stale data.
        await self._lock_namespace(namespace)
        result = await self.session.execute(
            select(SystemConfig).where(SystemConfig.key == namespace).with_for_update()
        )
        existing = result.scalar_one_or_none()
        db_data = existing.value if existing else None

        if self._allow_env:
            env_data = self._get_from_env(namespace, config_class)
            current = config_class(**{**env_data, **(db_data or {})})
        else:
            current = config_class(**(db_data or {}))

        # Apply updates
        updated = current.model_copy(update=updates)

        # Serialize and save
        # Use mode="json" for proper datetime serialization
        data = updated.model_dump(mode="json", exclude={"NAMESPACE"})
        if existing:
            existing.value = data
        else:
            self.session.add(SystemConfig(key=namespace, value=data))
        await self.session.commit()

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

        await self._lock_namespace(namespace)
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

    async def update_embedding_generation(
        self,
        *,
        expected_version: str | None,
        expected_rebuild_id: str | None,
        expected_statuses: set[str] | None = None,
        expected_values: dict[str, Any] | None = None,
        **updates: Any,
    ) -> EmbeddingConfig | None:
        """Atomically update only the matching embedding generation.

        Long-running provider calls and vector-store recreation can finish
        after an administrator has disabled, cancelled, or replaced the
        configuration.  Locking and checking the JSON row in one transaction
        prevents those stale workers from overwriting the newer lifecycle
        state.
        """
        from glean_core.schemas.config import EmbeddingConfig

        await self._lock_namespace(EmbeddingConfig.NAMESPACE)
        result = await self.session.execute(
            select(SystemConfig)
            .where(SystemConfig.key == EmbeddingConfig.NAMESPACE)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        row = result.scalar_one_or_none()
        current = EmbeddingConfig(**(row.value if row else {}))
        if (
            current.version != expected_version
            or current.rebuild_id != expected_rebuild_id
            or (expected_statuses is not None and current.status.value not in expected_statuses)
            or (
                expected_values is not None
                and any(
                    getattr(current, field_name) != expected_value
                    for field_name, expected_value in expected_values.items()
                )
            )
        ):
            await self.session.rollback()
            return None

        updated = current.model_copy(update=updates)
        data = updated.model_dump(mode="json", exclude={"NAMESPACE"})
        if row is None:
            self.session.add(SystemConfig(key=EmbeddingConfig.NAMESPACE, value=data))
        else:
            row.value = data
        await self.session.commit()
        return updated

    async def record_embedding_failure(
        self,
        *,
        expected_version: str | None,
        expected_rebuild_id: str | None,
        error: Exception,
        circuit_threshold: int,
    ) -> tuple[int, bool] | None:
        """Atomically count a failure for one active embedding generation."""
        from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus

        await self._lock_namespace(EmbeddingConfig.NAMESPACE)
        result = await self.session.execute(
            select(SystemConfig)
            .where(SystemConfig.key == EmbeddingConfig.NAMESPACE)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        row = result.scalar_one_or_none()
        current = EmbeddingConfig(**(row.value if row else {}))
        if (
            current.version != expected_version
            or current.rebuild_id != expected_rebuild_id
            or current.status not in (VectorizationStatus.IDLE, VectorizationStatus.REBUILDING)
        ):
            await self.session.rollback()
            return None

        error_count = current.error_count + 1
        circuit_open = error_count >= circuit_threshold
        updates: dict[str, Any] = {"error_count": error_count}
        if circuit_open:
            updates.update(
                status=VectorizationStatus.ERROR,
                last_error=f"Circuit breaker: {error}",
                last_error_at=datetime.now(UTC),
                rebuild_id=None,
                rebuild_started_at=None,
                rebuild_phase=None,
                target_vector_backend=None,
                target_vector_store_fingerprint=None,
                target_model_fingerprint=None,
                target_force_rebuild=False,
            )

        updated = current.model_copy(update=updates)
        data = updated.model_dump(mode="json", exclude={"NAMESPACE"})
        if row is None:
            self.session.add(SystemConfig(key=EmbeddingConfig.NAMESPACE, value=data))
        else:
            row.value = data
        await self.session.commit()
        return error_count, circuit_open

    async def reset_embedding_errors(
        self,
        *,
        expected_version: str | None,
        expected_rebuild_id: str | None,
    ) -> bool:
        """Reset the failure counter only for the generation that succeeded."""
        from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus

        await self._lock_namespace(EmbeddingConfig.NAMESPACE)
        result = await self.session.execute(
            select(SystemConfig)
            .where(SystemConfig.key == EmbeddingConfig.NAMESPACE)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        row = result.scalar_one_or_none()
        current = EmbeddingConfig(**(row.value if row else {}))
        if (
            current.version != expected_version
            or current.rebuild_id != expected_rebuild_id
            or current.status not in (VectorizationStatus.IDLE, VectorizationStatus.REBUILDING)
        ):
            await self.session.rollback()
            return False
        if current.error_count == 0:
            await self.session.rollback()
            return True

        updated = current.model_copy(update={"error_count": 0})
        if row is None:
            self.session.add(
                SystemConfig(
                    key=EmbeddingConfig.NAMESPACE,
                    value=updated.model_dump(mode="json", exclude={"NAMESPACE"}),
                )
            )
        else:
            row.value = updated.model_dump(mode="json", exclude={"NAMESPACE"})
        await self.session.commit()
        return True

    async def start_rebuild(self, expected_version: str | None = None) -> str | None:
        """
        Mark rebuild as started and return rebuild ID.

        Returns:
            The rebuild ID.
        """
        from glean_core.schemas.config import (
            EmbeddingConfig,
            EmbeddingRebuildPhase,
            VectorizationStatus,
        )

        rebuild_id = str(uuid.uuid4())
        current = await self.get(EmbeddingConfig)
        version = expected_version if expected_version is not None else current.version
        updated = await self.update_embedding_generation(
            expected_version=version,
            expected_rebuild_id=current.rebuild_id,
            expected_statuses={VectorizationStatus.VALIDATING.value},
            status=VectorizationStatus.REBUILDING,
            rebuild_id=rebuild_id,
            rebuild_started_at=datetime.now(UTC),
            rebuild_phase=EmbeddingRebuildPhase.PREPARING,
        )
        return rebuild_id if updated is not None else None

    async def complete_rebuild(self, expected_rebuild_id: str | None = None) -> bool:
        """Mark rebuild as completed if it is still the expected generation."""
        from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus

        current = await self.get(EmbeddingConfig)
        if expected_rebuild_id is not None and current.rebuild_id != expected_rebuild_id:
            return False

        updated = await self.update_embedding_generation(
            expected_version=current.version,
            expected_rebuild_id=current.rebuild_id,
            expected_statuses={VectorizationStatus.REBUILDING.value},
            status=VectorizationStatus.IDLE,
            rebuild_id=None,
            rebuild_started_at=None,
            rebuild_phase=None,
            error_count=0,
            last_error=None,
        )
        return updated is not None

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

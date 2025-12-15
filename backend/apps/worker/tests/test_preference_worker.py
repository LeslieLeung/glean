"""Tests for preference worker retry behavior."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arq import Retry

from glean_core.schemas.config import EmbeddingConfig, VectorizationStatus
from glean_worker.tasks.preference_worker import (
    _check_vectorization_enabled,
    rebuild_user_preference,
    update_user_preference,
)


class TestCheckVectorizationEnabled:
    """Test _check_vectorization_enabled function behavior with different states."""

    @pytest.mark.asyncio
    async def test_disabled_status_raises_value_error(self):
        """When vectorization is disabled, should raise ValueError (no retry)."""
        # Arrange
        mock_session = MagicMock()
        mock_config = EmbeddingConfig(
            enabled=False,
            status=VectorizationStatus.DISABLED,
            provider="sentence-transformers",
            model="test-model",
            dimension=384,
        )

        with patch("glean_worker.tasks.preference_worker.TypedConfigService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get.return_value = mock_config
            mock_service_class.return_value = mock_service

            # Act & Assert
            with pytest.raises(ValueError, match="Vectorization is disabled"):
                await _check_vectorization_enabled(mock_session)

    @pytest.mark.asyncio
    async def test_validating_status_raises_retry(self):
        """When vectorization is validating, should raise Retry with 30s defer."""
        # Arrange
        mock_session = MagicMock()
        mock_config = EmbeddingConfig(
            enabled=True,
            status=VectorizationStatus.VALIDATING,
            provider="sentence-transformers",
            model="test-model",
            dimension=384,
        )

        with patch("glean_worker.tasks.preference_worker.TypedConfigService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get.return_value = mock_config
            mock_service_class.return_value = mock_service

            # Act & Assert
            with pytest.raises(Retry) as exc_info:
                await _check_vectorization_enabled(mock_session)

            # Verify retry defer time is 30 seconds (defer_score is in milliseconds)
            retry_exception = exc_info.value
            assert retry_exception.defer_score == 30000  # 30 seconds in milliseconds

    @pytest.mark.asyncio
    async def test_error_status_raises_retry(self):
        """When vectorization is in ERROR state, should raise Retry with 2min defer."""
        # Arrange
        mock_session = MagicMock()
        mock_config = EmbeddingConfig(
            enabled=True,
            status=VectorizationStatus.ERROR,
            provider="sentence-transformers",
            model="test-model",
            dimension=384,
            last_error="Connection failed",
        )

        with patch("glean_worker.tasks.preference_worker.TypedConfigService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get.return_value = mock_config
            mock_service_class.return_value = mock_service

            # Act & Assert
            with pytest.raises(Retry) as exc_info:
                await _check_vectorization_enabled(mock_session)

            # Verify retry defer time is 2 minutes (defer_score is in milliseconds)
            retry_exception = exc_info.value
            assert retry_exception.defer_score == 120000  # 2 minutes in milliseconds

    @pytest.mark.asyncio
    async def test_idle_status_returns_config(self):
        """When vectorization is IDLE, should return config normally."""
        # Arrange
        mock_session = MagicMock()
        mock_config = EmbeddingConfig(
            enabled=True,
            status=VectorizationStatus.IDLE,
            provider="sentence-transformers",
            model="test-model",
            dimension=384,
        )

        with patch("glean_worker.tasks.preference_worker.TypedConfigService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get.return_value = mock_config
            mock_service_class.return_value = mock_service

            # Act
            result = await _check_vectorization_enabled(mock_session)

            # Assert
            assert result == mock_config

    @pytest.mark.asyncio
    async def test_rebuilding_status_returns_config(self):
        """When vectorization is REBUILDING, should return config normally."""
        # Arrange
        mock_session = MagicMock()
        mock_config = EmbeddingConfig(
            enabled=True,
            status=VectorizationStatus.REBUILDING,
            provider="sentence-transformers",
            model="test-model",
            dimension=384,
        )

        with patch("glean_worker.tasks.preference_worker.TypedConfigService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get.return_value = mock_config
            mock_service_class.return_value = mock_service

            # Act
            result = await _check_vectorization_enabled(mock_session)

            # Assert
            assert result == mock_config


class TestUpdateUserPreference:
    """Test update_user_preference task behavior with different vectorization states."""

    @pytest.mark.asyncio
    async def test_validating_state_propagates_retry(self):
        """When vectorization is validating, Retry exception should propagate to arq."""
        # Arrange
        ctx = {"milvus_client": MagicMock(), "redis": MagicMock()}
        mock_config = EmbeddingConfig(
            enabled=True,
            status=VectorizationStatus.VALIDATING,
            provider="sentence-transformers",
            model="test-model",
            dimension=384,
        )

        with (
            patch("glean_worker.tasks.preference_worker.get_session") as mock_get_session,
            patch("glean_worker.tasks.preference_worker.TypedConfigService") as mock_service_class,
        ):
            mock_session = AsyncMock()
            mock_get_session.return_value.__aiter__.return_value = [mock_session]

            mock_service = AsyncMock()
            mock_service.get.return_value = mock_config
            mock_service_class.return_value = mock_service

            # Act & Assert - Retry exception should propagate
            with pytest.raises(Retry):
                await update_user_preference(
                    ctx, user_id="test-user", entry_id="test-entry", signal_type="like"
                )

    @pytest.mark.asyncio
    async def test_disabled_state_returns_error_without_retry(self):
        """When vectorization is disabled, should return error dict without raising Retry."""
        # Arrange
        ctx = {"milvus_client": MagicMock(), "redis": MagicMock()}
        mock_config = EmbeddingConfig(
            enabled=False,
            status=VectorizationStatus.DISABLED,
            provider="sentence-transformers",
            model="test-model",
            dimension=384,
        )

        with (
            patch("glean_worker.tasks.preference_worker.get_session") as mock_get_session,
            patch("glean_worker.tasks.preference_worker.TypedConfigService") as mock_service_class,
        ):
            mock_session = AsyncMock()
            mock_get_session.return_value.__aiter__.return_value = [mock_session]

            mock_service = AsyncMock()
            mock_service.get.return_value = mock_config
            mock_service_class.return_value = mock_service

            # Act
            result = await update_user_preference(
                ctx, user_id="test-user", entry_id="test-entry", signal_type="like"
            )

            # Assert - Should return error dict, not raise exception
            assert result["success"] is False
            assert "disabled" in result["error"].lower()


class TestRebuildUserPreference:
    """Test rebuild_user_preference task behavior with different vectorization states."""

    @pytest.mark.asyncio
    async def test_error_state_propagates_retry(self):
        """When vectorization is in ERROR state, Retry exception should propagate."""
        # Arrange
        ctx = {"milvus_client": MagicMock(), "redis": MagicMock()}
        mock_config = EmbeddingConfig(
            enabled=True,
            status=VectorizationStatus.ERROR,
            provider="sentence-transformers",
            model="test-model",
            dimension=384,
            last_error="Provider unavailable",
        )

        with (
            patch("glean_worker.tasks.preference_worker.get_session") as mock_get_session,
            patch("glean_worker.tasks.preference_worker.TypedConfigService") as mock_service_class,
        ):
            mock_session = AsyncMock()
            mock_get_session.return_value.__aiter__.return_value = [mock_session]

            mock_service = AsyncMock()
            mock_service.get.return_value = mock_config
            mock_service_class.return_value = mock_service

            # Act & Assert - Retry exception should propagate
            with pytest.raises(Retry):
                await rebuild_user_preference(ctx, user_id="test-user")

    @pytest.mark.asyncio
    async def test_disabled_state_returns_error_without_retry(self):
        """When vectorization is disabled, should return error dict without raising Retry."""
        # Arrange
        ctx = {"milvus_client": MagicMock(), "redis": MagicMock()}
        mock_config = EmbeddingConfig(
            enabled=False,
            status=VectorizationStatus.DISABLED,
            provider="sentence-transformers",
            model="test-model",
            dimension=384,
        )

        with (
            patch("glean_worker.tasks.preference_worker.get_session") as mock_get_session,
            patch("glean_worker.tasks.preference_worker.TypedConfigService") as mock_service_class,
        ):
            mock_session = AsyncMock()
            mock_get_session.return_value.__aiter__.return_value = [mock_session]

            mock_service = AsyncMock()
            mock_service.get.return_value = mock_config
            mock_service_class.return_value = mock_service

            # Act
            result = await rebuild_user_preference(ctx, user_id="test-user")

            # Assert - Should return error dict, not raise exception
            assert result["success"] is False
            assert "disabled" in result["error"].lower()

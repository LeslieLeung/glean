"""Test error handling in MilvusClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pymilvus import MilvusException

from glean_vector.clients.milvus_client import MilvusClient


def _mock_collection(description: str, dimension: int = 1536) -> MagicMock:
    collection = MagicMock()
    collection.description = description
    vector_field = MagicMock()
    vector_field.name = "embedding"
    vector_field.params = {"dim": dimension}
    collection.schema.fields = [vector_field]
    return collection


class TestMilvusClientErrorHandling:
    """Test error handling in MilvusClient methods."""

    def test_check_model_compatibility_connection_error(self) -> None:
        """Test that check_model_compatibility handles connection errors gracefully."""
        client = MilvusClient()

        # Mock the connect method to raise ConnectionError
        with patch.object(client, "connect", side_effect=ConnectionError("Connection failed")):
            # Should return (True, None) instead of raising
            is_compatible, reason = client.check_model_compatibility(
                dimension=1536, provider="openai", model="text-embedding-3-small"
            )

            assert is_compatible is True
            assert reason is None

    def test_check_model_compatibility_milvus_exception(self) -> None:
        """Test that check_model_compatibility handles MilvusException gracefully."""
        client = MilvusClient()

        # Mock the connect method to raise MilvusException
        with patch.object(client, "connect", side_effect=MilvusException("Milvus error")):
            # Should return (True, None) instead of raising
            is_compatible, reason = client.check_model_compatibility(
                dimension=1536, provider="openai", model="text-embedding-3-small"
            )

            assert is_compatible is True
            assert reason is None

    def test_check_model_compatibility_collection_error(self) -> None:
        """Test that check_model_compatibility handles collection access errors gracefully."""
        client = MilvusClient()

        # Mock connect to succeed
        with (
            patch.object(client, "connect"),
            # Mock utility.has_collection to raise MilvusException
            patch(
                "glean_vector.clients.milvus_client.utility.has_collection",
                side_effect=MilvusException("Collection error"),
            ),
        ):
            # Should return (True, None) instead of raising
            is_compatible, reason = client.check_model_compatibility(
                dimension=1536, provider="openai", model="text-embedding-3-small"
            )

            assert is_compatible is True
            assert reason is None

    def test_collections_exist_connection_error(self) -> None:
        """Test that collections_exist handles connection errors gracefully."""
        client = MilvusClient()

        # Mock the connect method to raise ConnectionError
        with patch.object(client, "connect", side_effect=ConnectionError("Connection failed")):
            # Should return False instead of raising
            result = client.collections_exist()
            assert result is False

    def test_collections_exist_milvus_exception(self) -> None:
        """Test that collections_exist handles MilvusException gracefully."""
        client = MilvusClient()

        # Mock the connect method to raise MilvusException
        with patch.object(client, "connect", side_effect=MilvusException("Milvus error")):
            # Should return False instead of raising
            result = client.collections_exist()
            assert result is False

    def test_collections_exist_utility_error(self) -> None:
        """Test that collections_exist handles utility.has_collection errors gracefully."""
        client = MilvusClient()

        # Mock connect to succeed
        with (
            patch.object(client, "connect"),
            # Mock utility.has_collection to raise MilvusException
            patch(
                "glean_vector.clients.milvus_client.utility.has_collection",
                side_effect=MilvusException("Collection check error"),
            ),
        ):
            # Should return False instead of raising
            result = client.collections_exist()
            assert result is False

    def test_check_model_compatibility_partial_failure(self) -> None:
        """Test that check_model_compatibility continues checking when one collection fails."""
        client = MilvusClient()

        mock_collection = _mock_collection("Entry embeddings | model=openai:different-model:1536")

        # Mock connect to succeed
        with patch.object(client, "connect"):
            # Mock utility.has_collection to raise error for entries but succeed for prefs
            def has_collection_side_effect(name: str) -> bool:
                if name == client.config.entries_collection:
                    raise MilvusException("Entries collection error")
                return True  # Preferences collection exists

            with (
                patch(
                    "glean_vector.clients.milvus_client.utility.has_collection",
                    side_effect=has_collection_side_effect,
                ),
                patch(
                    "glean_vector.clients.milvus_client.Collection", return_value=mock_collection
                ),
            ):
                # Should handle entries error and check preferences
                is_compatible, reason = client.check_model_compatibility(
                    dimension=1536, provider="openai", model="text-embedding-3-small"
                )

                # Should detect incompatibility in preferences collection
                assert is_compatible is False
                assert reason is not None
                assert "Preferences collection" in reason

    def test_check_model_compatibility_accepts_legacy_unsigned_collection(self) -> None:
        """Legacy collections are compatible when their vector dimension matches."""
        client = MilvusClient()

        mock_collection = _mock_collection("Entry embeddings without signature")

        with (
            patch.object(client, "connect"),
            patch("glean_vector.clients.milvus_client.utility.has_collection", return_value=True),
            patch("glean_vector.clients.milvus_client.Collection", return_value=mock_collection),
        ):
            is_compatible, reason = client.check_model_compatibility(
                dimension=1536,
                provider="openai",
                model="text-embedding-3-small",
            )

        assert is_compatible is True
        assert reason is None

    def test_check_model_compatibility_rejects_dimension_mismatch(self) -> None:
        """Unsigned legacy collections must still use the requested dimension."""
        client = MilvusClient()
        mock_collection = _mock_collection("Legacy collection", dimension=384)

        with (
            patch.object(client, "connect"),
            patch("glean_vector.clients.milvus_client.utility.has_collection", return_value=True),
            patch("glean_vector.clients.milvus_client.Collection", return_value=mock_collection),
        ):
            is_compatible, reason = client.check_model_compatibility(
                dimension=1536,
                provider="openai",
                model="text-embedding-3-small",
            )

        assert is_compatible is False
        assert reason is not None
        assert "dimension mismatch" in reason

    @pytest.mark.asyncio
    async def test_ensure_collections_never_recreates_on_signature_mismatch(self) -> None:
        """Normal startup must not destroy collections created for another model."""
        client = MilvusClient()
        mock_collection = _mock_collection("Entry embeddings | model=openai:different-model:1536")

        with (
            patch.object(client, "connect"),
            patch("glean_vector.clients.milvus_client.utility.has_collection", return_value=True),
            patch("glean_vector.clients.milvus_client.Collection", return_value=mock_collection),
            patch.object(client, "recreate_collections", new=AsyncMock()) as recreate,
            patch("glean_vector.clients.milvus_client.utility.drop_collection") as drop,
            pytest.raises(RuntimeError, match="explicit vector rebuild"),
        ):
            await client.ensure_collections(
                dimension=1536,
                provider="openai",
                model="text-embedding-3-small",
            )

        recreate.assert_not_awaited()
        drop.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_collections_loads_legacy_unsigned_collections(self) -> None:
        """Normal startup may attach to compatible pre-signature collections."""
        client = MilvusClient()
        mock_collection = _mock_collection("Legacy collection")

        with (
            patch.object(client, "connect"),
            patch("glean_vector.clients.milvus_client.utility.has_collection", return_value=True),
            patch("glean_vector.clients.milvus_client.Collection", return_value=mock_collection),
            patch.object(client, "recreate_collections", new=AsyncMock()) as recreate,
        ):
            await client.ensure_collections(
                dimension=1536,
                provider="openai",
                model="text-embedding-3-small",
            )

        recreate.assert_not_awaited()
        assert mock_collection.load.call_count == 2

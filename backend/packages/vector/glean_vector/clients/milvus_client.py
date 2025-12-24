"""Milvus client for vector operations."""

import asyncio
from contextlib import suppress
from datetime import datetime
from typing import Any

from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    MilvusException,
    connections,
    utility,
)

from glean_core import get_logger
from glean_vector.config import milvus_config

logger = get_logger(__name__)


class MilvusClient:
    """
    Milvus vector database client.

    Manages connections and operations for entry embeddings and user preferences.
    """

    def __init__(self) -> None:
        """Initialize Milvus client."""
        self.config = milvus_config
        self._connected = False
        self._entries_collection: Collection | None = None
        self._prefs_collection: Collection | None = None

    @staticmethod
    def _escape_string(s: str) -> str:
        """
        Escape special characters in strings for Milvus filter expressions.

        Args:
            s: String to escape

        Returns:
            Escaped string safe for use in filter expressions
        """
        # Escape double quotes and backslashes
        return s.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _build_model_signature(provider: str, model: str, dimension: int) -> str:
        """
        Build a unique signature for the embedding model configuration.

        Args:
            provider: Embedding provider (e.g., "openai", "volcengine")
            model: Model name (e.g., "text-embedding-3-small")
            dimension: Vector dimension

        Returns:
            Model signature string
        """
        return f"{provider}:{model}:{dimension}"

    @staticmethod
    def _extract_model_signature(collection: Collection) -> str | None:
        """
        Extract model signature from collection description.

        Args:
            collection: Milvus collection

        Returns:
            Model signature or None if not found
        """
        try:
            description = collection.description
            # Look for pattern "model=provider:model:dimension"
            if "model=" in description:
                parts = description.split("model=")
                if len(parts) > 1:
                    signature = parts[1].split()[0]  # Get first token after "model="
                    return signature
        except Exception:
            pass
        return None

    def check_model_compatibility(
        self, dimension: int, provider: str, model: str
    ) -> tuple[bool, str | None]:
        """
        Check if existing Milvus collections are compatible with the target model config.

        This is used to determine if a rebuild is necessary when enabling/updating
        vectorization config. If the collections already match the target model,
        no rebuild is needed.

        Args:
            dimension: Target vector dimension
            provider: Target embedding provider
            model: Target model name

        Returns:
            Tuple of (is_compatible, reason):
            - (True, None) if collections match or don't exist
            - (False, reason) if collections exist but don't match
        """
        # Try to connect to Milvus
        try:
            self.connect()
        except (MilvusException, ConnectionError) as e:
            logger.warning(f"Failed to connect to Milvus for compatibility check: {e}")
            # Assume compatible if we can't check (fail-safe approach)
            return (True, None)

        expected_signature = self._build_model_signature(provider, model, dimension)

        # Check entries collection
        try:
            if utility.has_collection(self.config.entries_collection):  # type: ignore[truthy-function]
                collection = Collection(self.config.entries_collection)
                existing_signature = self._extract_model_signature(collection)
                if existing_signature and existing_signature != expected_signature:
                    return (
                        False,
                        f"Entries collection signature mismatch: "
                        f"existing={existing_signature}, expected={expected_signature}",
                    )
        except MilvusException as e:
            logger.warning(
                f"Failed to check entries collection compatibility: {e}. Assuming compatible."
            )
            # Continue to check preferences collection

        # Check preferences collection
        try:
            if utility.has_collection(self.config.prefs_collection):  # type: ignore[truthy-function]
                collection = Collection(self.config.prefs_collection)
                existing_signature = self._extract_model_signature(collection)
                if existing_signature and existing_signature != expected_signature:
                    return (
                        False,
                        f"Preferences collection signature mismatch: "
                        f"existing={existing_signature}, expected={expected_signature}",
                    )
        except MilvusException as e:
            logger.warning(
                f"Failed to check preferences collection compatibility: {e}. Assuming compatible."
            )

        return (True, None)

    def collections_exist(self) -> bool:
        """
        Check if both required Milvus collections exist.

        Returns:
            True if both entries and preferences collections exist
        """
        try:
            self.connect()
            entries_exist = utility.has_collection(self.config.entries_collection)  # type: ignore[truthy-function]
            prefs_exist = utility.has_collection(self.config.prefs_collection)  # type: ignore[truthy-function]
            return bool(entries_exist and prefs_exist)  # type: ignore[reportUnknownArgumentType]
        except (MilvusException, ConnectionError) as e:
            logger.warning(f"Failed to check if collections exist: {e}")
            return False

    def connect(self) -> None:
        """Establish connection to Milvus."""
        # Check if actually connected (not just the flag, but real connection status)
        # pymilvus connections are global by alias, so another client might have disconnected
        if self._connected and connections.has_connection("default"):
            return

        try:
            connections.connect(  # type: ignore[reportUnknownMemberType]
                alias="default",
                host=self.config.host,
                port=str(self.config.port),
                user=self.config.user or "",
                password=self.config.password or "",
            )
            self._connected = True
        except MilvusException as e:
            raise ConnectionError(f"Failed to connect to Milvus: {e}") from e

    def disconnect(self) -> None:
        """Close connection to Milvus."""
        if self._connected:
            connections.disconnect("default")
            self._connected = False

    async def ensure_collections(
        self, dimension: int, provider: str | None = None, model: str | None = None
    ) -> None:
        """
        Ensure required collections exist with correct model configuration.

        If collections exist but were created for a different model (even with same dimension),
        they will be recreated to ensure embedding compatibility.

        Args:
            dimension: Vector dimension for embeddings
            provider: Embedding provider (optional, for model validation)
            model: Model name (optional, for model validation)
        """
        self.connect()

        # Build expected model signature if provider and model are provided
        expected_signature = None
        if provider and model:
            expected_signature = self._build_model_signature(provider, model, dimension)

        # Check entries collection
        if utility.has_collection(self.config.entries_collection):  # type: ignore[truthy-function]
            collection = Collection(self.config.entries_collection)

            # Check if model has changed
            if expected_signature:
                existing_signature = self._extract_model_signature(collection)
                if existing_signature and existing_signature != expected_signature:
                    # Model changed - recreate collections
                    await self.recreate_collections(dimension, provider, model)
                    return

            self._entries_collection = collection
            self._entries_collection.load()  # type: ignore[unused-coroutine]
        else:
            self._entries_collection = self._create_entries_collection(dimension, provider, model)

        # Check preferences collection
        if utility.has_collection(self.config.prefs_collection):  # type: ignore[truthy-function]
            collection = Collection(self.config.prefs_collection)

            # Check if model has changed
            if expected_signature:
                existing_signature = self._extract_model_signature(collection)
                if existing_signature and existing_signature != expected_signature:
                    # Model changed - recreate collections
                    await self.recreate_collections(dimension, provider, model)
                    return

            self._prefs_collection = collection
            self._prefs_collection.load()  # type: ignore[unused-coroutine]
        else:
            self._prefs_collection = self._create_user_preferences_collection(
                dimension, provider, model
            )

    async def recreate_collections(
        self, dimension: int, provider: str | None = None, model: str | None = None
    ) -> None:
        """
        Drop and recreate collections with the specified model configuration.

        Args:
            dimension: Vector dimension for embeddings
            provider: Embedding provider (optional, stored in collection metadata)
            model: Model name (optional, stored in collection metadata)
        """
        self.connect()

        # Drop existing collections if present
        if utility.has_collection(self.config.entries_collection):  # type: ignore[truthy-function]
            utility.drop_collection(self.config.entries_collection)  # type: ignore[unused-coroutine]
            # Wait for drop to complete with longer timeout
            for i in range(30):  # Increased from 10 to 30
                if not utility.has_collection(self.config.entries_collection):  # type: ignore[truthy-function]
                    break
                await asyncio.sleep(0.2)  # Non-blocking async sleep
                if i == 29:
                    raise RuntimeError(
                        f"Timeout waiting for collection {self.config.entries_collection} to drop"
                    )

        if utility.has_collection(self.config.prefs_collection):  # type: ignore[truthy-function]
            utility.drop_collection(self.config.prefs_collection)  # type: ignore[unused-coroutine]
            # Wait for drop to complete with longer timeout
            for i in range(30):  # Increased from 10 to 30
                if not utility.has_collection(self.config.prefs_collection):  # type: ignore[truthy-function]
                    break
                await asyncio.sleep(0.2)  # Non-blocking async sleep
                if i == 29:
                    raise RuntimeError(
                        f"Timeout waiting for collection {self.config.prefs_collection} to drop"
                    )

        # Additional wait to ensure Milvus state is fully updated
        await asyncio.sleep(0.5)  # Non-blocking async sleep

        # Recreate with model metadata
        self._entries_collection = self._create_entries_collection(dimension, provider, model)
        self._prefs_collection = self._create_user_preferences_collection(
            dimension, provider, model
        )

    def _create_entries_collection(
        self, dimension: int, provider: str | None = None, model: str | None = None
    ) -> Collection:
        """
        Create Milvus collection for entry embeddings.

        Args:
            dimension: Vector dimension
            provider: Embedding provider (stored in description)
            model: Model name (stored in description)

        Returns:
            Created collection
        """
        # If collection already exists with same signature, just load and return it
        if utility.has_collection(self.config.entries_collection):  # type: ignore[truthy-function]
            existing_collection = Collection(self.config.entries_collection)
            if provider and model:
                existing_signature = self._extract_model_signature(existing_collection)
                expected_signature = self._build_model_signature(provider, model, dimension)
                if existing_signature == expected_signature:
                    existing_collection.load()  # type: ignore[unused-coroutine]
                    return existing_collection
            # If signatures don't match or no signature check, we have a problem
            # This shouldn't happen if recreate_collections worked properly
            raise RuntimeError(
                f"Collection {self.config.entries_collection} already exists with different configuration"
            )

        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=36, is_primary=True),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dimension),
            FieldSchema(name="feed_id", dtype=DataType.VARCHAR, max_length=36),
            FieldSchema(name="published_at", dtype=DataType.INT64),
            FieldSchema(name="language", dtype=DataType.VARCHAR, max_length=10),
            FieldSchema(name="word_count", dtype=DataType.INT32),
            FieldSchema(name="author", dtype=DataType.VARCHAR, max_length=200),
        ]

        # Build description with model signature
        description = "Entry embeddings for semantic search"
        if provider and model:
            signature = self._build_model_signature(provider, model, dimension)
            description += f" | model={signature}"

        schema = CollectionSchema(fields=fields, description=description)
        collection = Collection(name=self.config.entries_collection, schema=schema)

        # Create index for vector search
        collection.create_index(  # type: ignore[unused-coroutine]
            "embedding",
            {"index_type": "IVF_FLAT", "metric_type": "COSINE", "params": {"nlist": 1024}},
        )

        # Create indexes for filtering with error handling
        try:
            # Check if index already exists before creating
            existing_indexes = {idx.field_name: idx for idx in collection.indexes}

            if "feed_id" not in existing_indexes:
                collection.create_index("feed_id", index_name="idx_feed_id")  # type: ignore[unused-coroutine]

            if "published_at" not in existing_indexes:
                collection.create_index("published_at", index_name="idx_published_at")  # type: ignore[unused-coroutine]
        except MilvusException as e:
            # If index creation fails, log but don't fail the whole operation
            # Indexes are optional for basic functionality
            logger.warning("Failed to create scalar indexes", extra={"error": str(e)})

        collection.load()  # type: ignore[unused-coroutine]
        return collection

    def _create_user_preferences_collection(
        self, dimension: int, provider: str | None = None, model: str | None = None
    ) -> Collection:
        """
        Create Milvus collection for user preference vectors.

        Args:
            dimension: Vector dimension
            provider: Embedding provider (stored in description)
            model: Model name (stored in description)

        Returns:
            Created collection
        """
        # If collection already exists with same signature, just load and return it
        if utility.has_collection(self.config.prefs_collection):  # type: ignore[truthy-function]
            existing_collection = Collection(self.config.prefs_collection)
            if provider and model:
                existing_signature = self._extract_model_signature(existing_collection)
                expected_signature = self._build_model_signature(provider, model, dimension)
                if existing_signature == expected_signature:
                    existing_collection.load()  # type: ignore[unused-coroutine]
                    return existing_collection
            # If signatures don't match or no signature check, we have a problem
            raise RuntimeError(
                f"Collection {self.config.prefs_collection} already exists with different configuration"
            )

        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=50, is_primary=True),
            FieldSchema(name="user_id", dtype=DataType.VARCHAR, max_length=36),
            FieldSchema(name="vector_type", dtype=DataType.VARCHAR, max_length=20),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dimension),
            FieldSchema(name="sample_count", dtype=DataType.FLOAT),
            FieldSchema(name="updated_at", dtype=DataType.INT64),
        ]

        # Build description with model signature
        description = "User preference vectors for recommendations"
        if provider and model:
            signature = self._build_model_signature(provider, model, dimension)
            description += f" | model={signature}"

        schema = CollectionSchema(fields=fields, description=description)
        collection = Collection(name=self.config.prefs_collection, schema=schema)

        # Simple FLAT index for small preference set
        collection.create_index("embedding", {"index_type": "FLAT", "metric_type": "COSINE"})  # type: ignore[unused-coroutine]

        # Create index for user_id with error handling
        try:
            # Check if index already exists before creating
            existing_indexes = {idx.field_name: idx for idx in collection.indexes}

            if "user_id" not in existing_indexes:
                collection.create_index("user_id", index_name="idx_user_id")  # type: ignore[unused-coroutine]
        except MilvusException as e:
            # If index creation fails, log but don't fail the whole operation
            logger.warning("Failed to create user_id index", extra={"error": str(e)})

        collection.load()  # type: ignore[reportUnknownMemberType]
        return collection

    def _is_collection_not_found_error(self, e: MilvusException) -> bool:
        """
        Check if the exception is a "collection not found" error.

        This can happen when the collection was dropped and recreated by another task
        (e.g., during model rebuild), leaving stale Collection object references.

        Args:
            e: MilvusException to check

        Returns:
            True if this is a collection not found error
        """
        # Milvus error code 100 = collection not found
        return e.code == 100 or "collection not found" in str(e).lower()

    def _refresh_entries_collection(self) -> None:
        """
        Refresh the entries collection reference.

        This reloads the Collection object to get the current internal ID
        after a potential drop/recreate by another task.
        """
        self.connect()
        if utility.has_collection(self.config.entries_collection):  # type: ignore[truthy-function]
            self._entries_collection = Collection(self.config.entries_collection)
            self._entries_collection.load()  # type: ignore[unused-coroutine]
        else:
            self._entries_collection = None

    def _refresh_prefs_collection(self) -> None:
        """
        Refresh the preferences collection reference.

        This reloads the Collection object to get the current internal ID
        after a potential drop/recreate by another task.
        """
        self.connect()
        if utility.has_collection(self.config.prefs_collection):  # type: ignore[truthy-function]
            self._prefs_collection = Collection(self.config.prefs_collection)
            self._prefs_collection.load()  # type: ignore[unused-coroutine]
        else:
            self._prefs_collection = None

    async def insert_entry_embedding(
        self,
        entry_id: str,
        embedding: list[float],
        feed_id: str,
        published_at: datetime | None = None,
        language: str = "",
        word_count: int = 0,
        author: str = "",
    ) -> None:
        """
        Insert or update entry embedding.

        Args:
            entry_id: Entry UUID
            embedding: Vector embedding
            feed_id: Feed UUID
            published_at: Publication timestamp
            language: Content language code
            word_count: Word count
            author: Author name
        """
        if not self._entries_collection:
            raise RuntimeError("Collections not initialized. Call ensure_collections() first.")

        published_ts = (
            int(published_at.timestamp()) if published_at else int(datetime.now().timestamp())
        )

        # Delete existing entry if present (upsert pattern)
        # Entry might not exist, ignore
        with suppress(MilvusException):
            self._entries_collection.delete(expr=f'id == "{self._escape_string(entry_id)}"')  # type: ignore[reportUnknownMemberType]

        data = [
            [entry_id],
            [embedding],
            [feed_id],
            [published_ts],
            [language or ""],
            [word_count],
            [author or ""],
        ]

        try:
            self._entries_collection.insert(data)  # type: ignore[reportUnknownMemberType]
        except MilvusException as e:
            # Collection may have been dropped and recreated by another task (rebuild)
            # Refresh the collection reference and retry once
            if self._is_collection_not_found_error(e):
                self._refresh_entries_collection()
                if not self._entries_collection:
                    raise RuntimeError(
                        "Entries collection does not exist. "
                        "It may have been dropped during a rebuild."
                    ) from e
                self._entries_collection.insert(data)  # type: ignore[reportUnknownMemberType]
            else:
                raise

    async def get_entry_embedding(self, entry_id: str) -> list[float] | None:
        """
        Get embedding for an entry.

        Args:
            entry_id: Entry UUID

        Returns:
            Embedding vector or None if not found
        """
        if not self._entries_collection:
            raise RuntimeError("Collections not initialized. Call ensure_collections() first.")

        results = self._entries_collection.query(  # type: ignore[assignment]
            expr=f'id == "{self._escape_string(entry_id)}"', output_fields=["embedding"]
        )

        if results:  # type: ignore[truthy-function]
            return results[0]["embedding"]  # type: ignore[index]
        return None

    async def batch_get_entry_embeddings(self, entry_ids: list[str]) -> dict[str, list[float]]:
        """
        Get embeddings for multiple entries in batch.

        Args:
            entry_ids: List of Entry UUIDs

        Returns:
            Dictionary mapping entry_id to embedding vector
        """
        if not self._entries_collection:
            raise RuntimeError("Collections not initialized. Call ensure_collections() first.")

        if not entry_ids:
            return {}

        # Build IN expression for batch query
        ids_str = ", ".join(f'"{self._escape_string(eid)}"' for eid in entry_ids)
        expr = f"id in [{ids_str}]"

        results = self._entries_collection.query(expr=expr, output_fields=["id", "embedding"])  # type: ignore[assignment]

        return {result["id"]: result["embedding"] for result in results}  # type: ignore[misc]

    async def search_similar_entries(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search for similar entries.

        Args:
            query_vector: Query embedding
            top_k: Number of results to return
            filters: Optional filters (feed_id, published_at, etc.)

        Returns:
            List of similar entries with scores
        """
        if not self._entries_collection:
            raise RuntimeError("Collections not initialized. Call ensure_collections() first.")

        search_params = {"metric_type": "COSINE", "params": {"nprobe": 10}}

        # Build filter expression
        expr = None
        if filters:
            conditions: list[str] = []
            if "feed_id" in filters:
                conditions.append(f'feed_id == "{self._escape_string(filters["feed_id"])}"')
            if "min_published_at" in filters:
                ts = int(filters["min_published_at"].timestamp())
                conditions.append(f"published_at >= {ts}")
            if conditions:
                expr = " && ".join(conditions)

        results = self._entries_collection.search(  # type: ignore[assignment]
            data=[query_vector],
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            expr=expr,
            output_fields=["id", "feed_id", "published_at", "author"],
        )

        return [
            {
                "id": hit.id,  # type: ignore[misc]
                "score": hit.score,  # type: ignore[misc]
                "feed_id": hit.entity.get("feed_id"),  # type: ignore[misc]
                "published_at": hit.entity.get("published_at"),  # type: ignore[misc]
                "author": hit.entity.get("author"),  # type: ignore[misc]
            }
            for hit in results[0]  # type: ignore[index]
        ]

    async def upsert_user_preference(
        self,
        user_id: str,
        vector_type: str,
        embedding: list[float],
        sample_count: float,
        updated_at: int,
    ) -> None:
        """
        Insert or update user preference vector.

        Args:
            user_id: User UUID
            vector_type: "positive" or "negative"
            embedding: Preference vector
            sample_count: Number of samples used
            updated_at: Update timestamp (unix)
        """
        if not self._prefs_collection:
            raise RuntimeError("Collections not initialized. Call ensure_collections() first.")

        pref_id = f"{user_id}_{vector_type}"

        # Delete existing if present
        with suppress(MilvusException):
            self._prefs_collection.delete(expr=f'id == "{self._escape_string(pref_id)}"')  # type: ignore[unused-coroutine]

        # Insert new
        data = [
            [pref_id],
            [user_id],
            [vector_type],
            [embedding],
            [sample_count],
            [updated_at],
        ]

        try:
            self._prefs_collection.insert(data)  # type: ignore[reportUnknownMemberType]
        except MilvusException as e:
            # Collection may have been dropped and recreated by another task (rebuild)
            # Refresh the collection reference and retry once
            if self._is_collection_not_found_error(e):
                self._refresh_prefs_collection()
                if not self._prefs_collection:
                    raise RuntimeError(
                        "Preferences collection does not exist. "
                        "It may have been dropped during a rebuild."
                    ) from e
                self._prefs_collection.insert(data)  # type: ignore[reportUnknownMemberType]
            else:
                raise

    async def get_user_preferences(self, user_id: str) -> dict[str, dict[str, Any]]:
        """
        Get user preference vectors.

        Args:
            user_id: User UUID

        Returns:
            Dictionary with "positive" and "negative" preference data
        """
        if not self._prefs_collection:
            raise RuntimeError("Collections not initialized. Call ensure_collections() first.")

        results = self._prefs_collection.query(  # type: ignore[assignment]
            expr=f'user_id == "{self._escape_string(user_id)}"',
            output_fields=["vector_type", "embedding", "sample_count", "updated_at"],
        )

        prefs: dict[str, dict[str, Any]] = {}
        for result in results:  # type: ignore[misc]
            vector_type = result["vector_type"]  # type: ignore[index]
            prefs[vector_type] = {
                "embedding": result["embedding"],  # type: ignore[index]
                "sample_count": result["sample_count"],  # type: ignore[index]
                "updated_at": result["updated_at"],  # type: ignore[index]
            }

        return prefs

    async def delete_entry_embedding(self, entry_id: str) -> None:
        """
        Delete entry embedding.

        Args:
            entry_id: Entry UUID
        """
        if not self._entries_collection:
            raise RuntimeError("Collections not initialized. Call ensure_collections() first.")

        self._entries_collection.delete(expr=f'id == "{self._escape_string(entry_id)}"')  # type: ignore[unused-coroutine]

    async def delete_user_preferences(self, user_id: str) -> None:
        """
        Delete all preference vectors for a user.

        Args:
            user_id: User UUID
        """
        if not self._prefs_collection:
            raise RuntimeError("Collections not initialized. Call ensure_collections() first.")

        self._prefs_collection.delete(expr=f'user_id == "{self._escape_string(user_id)}"')  # type: ignore[unused-coroutine]

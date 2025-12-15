"""Milvus client for vector operations."""

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

from glean_vector.config import milvus_config


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

    def connect(self) -> None:
        """Establish connection to Milvus."""
        # Check if actually connected (not just the flag, but real connection status)
        # pymilvus connections are global by alias, so another client might have disconnected
        if self._connected and connections.has_connection("default"):
            return

        try:
            connections.connect(
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

    def ensure_collections(
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
        if utility.has_collection(self.config.entries_collection):
            collection = Collection(self.config.entries_collection)

            # Check if model has changed
            if expected_signature:
                existing_signature = self._extract_model_signature(collection)
                if existing_signature and existing_signature != expected_signature:
                    # Model changed - recreate collections
                    self.recreate_collections(dimension, provider, model)
                    return

            self._entries_collection = collection
            self._entries_collection.load()
        else:
            self._entries_collection = self._create_entries_collection(
                dimension, provider, model
            )

        # Check preferences collection
        if utility.has_collection(self.config.prefs_collection):
            collection = Collection(self.config.prefs_collection)

            # Check if model has changed
            if expected_signature:
                existing_signature = self._extract_model_signature(collection)
                if existing_signature and existing_signature != expected_signature:
                    # Model changed - recreate collections
                    self.recreate_collections(dimension, provider, model)
                    return

            self._prefs_collection = collection
            self._prefs_collection.load()
        else:
            self._prefs_collection = self._create_user_preferences_collection(
                dimension, provider, model
            )

    def recreate_collections(
        self, dimension: int, provider: str | None = None, model: str | None = None
    ) -> None:
        """
        Drop and recreate collections with the specified model configuration.

        Args:
            dimension: Vector dimension for embeddings
            provider: Embedding provider (optional, stored in collection metadata)
            model: Model name (optional, stored in collection metadata)
        """
        import time

        self.connect()

        # Drop existing collections if present
        if utility.has_collection(self.config.entries_collection):
            utility.drop_collection(self.config.entries_collection)
            # Wait for drop to complete with longer timeout
            for i in range(30):  # Increased from 10 to 30
                if not utility.has_collection(self.config.entries_collection):
                    break
                time.sleep(0.2)  # Increased from 0.1 to 0.2
                if i == 29:
                    raise RuntimeError(
                        f"Timeout waiting for collection {self.config.entries_collection} to drop"
                    )

        if utility.has_collection(self.config.prefs_collection):
            utility.drop_collection(self.config.prefs_collection)
            # Wait for drop to complete with longer timeout
            for i in range(30):  # Increased from 10 to 30
                if not utility.has_collection(self.config.prefs_collection):
                    break
                time.sleep(0.2)  # Increased from 0.1 to 0.2
                if i == 29:
                    raise RuntimeError(
                        f"Timeout waiting for collection {self.config.prefs_collection} to drop"
                    )

        # Additional wait to ensure Milvus state is fully updated
        time.sleep(0.5)

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
        if utility.has_collection(self.config.entries_collection):
            existing_collection = Collection(self.config.entries_collection)
            if provider and model:
                existing_signature = self._extract_model_signature(existing_collection)
                expected_signature = self._build_model_signature(provider, model, dimension)
                if existing_signature == expected_signature:
                    existing_collection.load()
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
        collection.create_index(
            "embedding",
            {"index_type": "IVF_FLAT", "metric_type": "COSINE", "params": {"nlist": 1024}},
        )

        # Create indexes for filtering with error handling
        try:
            # Check if index already exists before creating
            existing_indexes = {idx.field_name: idx for idx in collection.indexes}
            
            if "feed_id" not in existing_indexes:
                collection.create_index("feed_id", index_name="idx_feed_id")
            
            if "published_at" not in existing_indexes:
                collection.create_index("published_at", index_name="idx_published_at")
        except MilvusException as e:
            # If index creation fails, log but don't fail the whole operation
            # Indexes are optional for basic functionality
            print(f"Warning: Failed to create scalar indexes: {e}")

        collection.load()
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
        if utility.has_collection(self.config.prefs_collection):
            existing_collection = Collection(self.config.prefs_collection)
            if provider and model:
                existing_signature = self._extract_model_signature(existing_collection)
                expected_signature = self._build_model_signature(provider, model, dimension)
                if existing_signature == expected_signature:
                    existing_collection.load()
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
        collection.create_index(
            "embedding", {"index_type": "FLAT", "metric_type": "COSINE"}
        )
        
        # Create index for user_id with error handling
        try:
            # Check if index already exists before creating
            existing_indexes = {idx.field_name: idx for idx in collection.indexes}
            
            if "user_id" not in existing_indexes:
                collection.create_index("user_id", index_name="idx_user_id")
        except MilvusException as e:
            # If index creation fails, log but don't fail the whole operation
            print(f"Warning: Failed to create user_id index: {e}")

        collection.load()
        return collection

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
        try:
            self._entries_collection.delete(expr=f'id == "{entry_id}"')
        except MilvusException:
            pass  # Entry might not exist, ignore

        data = [
            [entry_id],
            [embedding],
            [feed_id],
            [published_ts],
            [language or ""],
            [word_count],
            [author or ""],
        ]

        self._entries_collection.insert(data)

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

        results = self._entries_collection.query(
            expr=f'id == "{entry_id}"', output_fields=["embedding"]
        )

        if results:
            return results[0]["embedding"]
        return None

    async def batch_get_entry_embeddings(
        self, entry_ids: list[str]
    ) -> dict[str, list[float]]:
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
        ids_str = ", ".join(f'"{eid}"' for eid in entry_ids)
        expr = f"id in [{ids_str}]"

        results = self._entries_collection.query(
            expr=expr, output_fields=["id", "embedding"]
        )

        return {result["id"]: result["embedding"] for result in results}

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
            conditions = []
            if "feed_id" in filters:
                conditions.append(f'feed_id == "{filters["feed_id"]}"')
            if "min_published_at" in filters:
                ts = int(filters["min_published_at"].timestamp())
                conditions.append(f"published_at >= {ts}")
            if conditions:
                expr = " && ".join(conditions)

        results = self._entries_collection.search(
            data=[query_vector],
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            expr=expr,
            output_fields=["id", "feed_id", "published_at", "author"],
        )

        return [
            {
                "id": hit.id,
                "score": hit.score,
                "feed_id": hit.entity.get("feed_id"),
                "published_at": hit.entity.get("published_at"),
                "author": hit.entity.get("author"),
            }
            for hit in results[0]
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
        self._prefs_collection.delete(expr=f'id == "{pref_id}"')

        # Insert new
        data = [
            [pref_id],
            [user_id],
            [vector_type],
            [embedding],
            [sample_count],
            [updated_at],
        ]

        self._prefs_collection.insert(data)

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

        results = self._prefs_collection.query(
            expr=f'user_id == "{user_id}"',
            output_fields=["vector_type", "embedding", "sample_count", "updated_at"],
        )

        prefs: dict[str, dict[str, Any]] = {}
        for result in results:
            vector_type = result["vector_type"]
            prefs[vector_type] = {
                "embedding": result["embedding"],
                "sample_count": result["sample_count"],
                "updated_at": result["updated_at"],
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

        self._entries_collection.delete(expr=f'id == "{entry_id}"')

    async def delete_user_preferences(self, user_id: str) -> None:
        """
        Delete all preference vectors for a user.

        Args:
            user_id: User UUID
        """
        if not self._prefs_collection:
            raise RuntimeError("Collections not initialized. Call ensure_collections() first.")

        self._prefs_collection.delete(expr=f'user_id == "{user_id}"')

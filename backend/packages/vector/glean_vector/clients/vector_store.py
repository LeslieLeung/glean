"""Vector store client abstractions and factory."""

from __future__ import annotations

from typing import Any, Protocol

from glean_vector.config import vector_backend_config


class VectorStoreClient(Protocol):
    """Backend-agnostic vector store interface."""

    def connect(self) -> None:
        """Establish backend connection or initialize resources."""

    async def disconnect(self) -> None:
        """Close backend connection/resources."""

    async def ensure_collections(
        self, dimension: int, provider: str | None = None, model: str | None = None
    ) -> None:
        """Ensure storage structures exist and match active model config."""

    async def recreate_collections(
        self, dimension: int, provider: str | None = None, model: str | None = None
    ) -> None:
        """Drop and recreate storage structures for full rebuild."""

    def check_model_compatibility(
        self, dimension: int, provider: str, model: str
    ) -> tuple[bool, str | None]:
        """Check whether existing vector data is compatible with model config."""
        ...

    def collections_exist(self) -> bool:
        """Return whether required vector storage structures already exist."""
        ...

    async def insert_entry_embedding(
        self,
        entry_id: str,
        embedding: list[float],
        feed_id: str,
        published_at: Any | None = None,
        language: str = "",
        word_count: int = 0,
        author: str = "",
    ) -> None:
        """Insert or update an entry embedding."""

    async def get_entry_embedding(self, entry_id: str) -> list[float] | None:
        """Get embedding for one entry."""

    async def batch_get_entry_embeddings(self, entry_ids: list[str]) -> dict[str, list[float]]:
        """Get embeddings for multiple entries."""
        ...

    async def search_similar_entries(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Search similar entries with optional filters."""
        ...

    async def upsert_user_preference(
        self,
        user_id: str,
        vector_type: str,
        embedding: list[float],
        sample_count: float,
        updated_at: int,
    ) -> None:
        """Insert or update a user preference vector."""

    async def get_user_preferences(self, user_id: str) -> dict[str, dict[str, Any]]:
        """Get all preference vectors for a user."""
        ...

    async def delete_entry_embedding(self, entry_id: str) -> None:
        """Delete one entry embedding."""

    async def delete_user_preferences(self, user_id: str) -> None:
        """Delete all preference vectors for a user."""


def create_vector_store_client() -> VectorStoreClient:
    """Create vector store client from configured backend."""
    backend = vector_backend_config.backend.lower()
    if backend == "milvus":
        from glean_vector.clients.milvus_client import MilvusClient

        return MilvusClient()
    if backend == "pgvector":
        from glean_vector.clients.pgvector_client import PgVectorClient

        return PgVectorClient()
    raise ValueError(f"Unsupported vector backend: {vector_backend_config.backend}")

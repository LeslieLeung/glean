"""Clients for external services."""

from glean_vector.clients.embedding_client import EmbeddingClient
from glean_vector.clients.milvus_client import MilvusClient

__all__ = ["EmbeddingClient", "MilvusClient"]

"""Basic tests for PgVectorClient behavior."""

from glean_vector.clients.pgvector_client import PgVectorClient


def test_pgvector_client_defaults_require_rebuild() -> None:
    """Compatibility checks default to rebuild-required path."""
    client = PgVectorClient()
    compatible, reason = client.check_model_compatibility(1536, "openai", "text-embedding-3-small")
    assert compatible is False
    assert reason is not None


def test_pgvector_client_collections_exist_defaults_false() -> None:
    """collections_exist returns False before backend initialization."""
    client = PgVectorClient()
    assert client.collections_exist() is False

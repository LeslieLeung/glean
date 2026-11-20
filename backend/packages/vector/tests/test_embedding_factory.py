"""Test supported embedding providers without external API calls."""

import pytest

from glean_vector.clients.embedding_factory import EmbeddingProviderFactory
from glean_vector.clients.providers import OpenAIProvider, VolcEngineProvider
from glean_vector.config import EmbeddingConfig


@pytest.mark.parametrize(
    ("name", "provider_class"),
    [
        ("openai", OpenAIProvider),
        ("volc-engine", VolcEngineProvider),
        ("volc_engine", VolcEngineProvider),
        ("volcengine", VolcEngineProvider),
    ],
)
def test_create_remote_provider(name: str, provider_class: type) -> None:
    config = EmbeddingConfig(
        provider=name,
        model="remote-model",
        dimension=1024,
        base_url="https://embeddings.example/v1",
        api_key="test-key",
        batch_size=4,
    )

    provider = EmbeddingProviderFactory.create(config=config, batch_size=2)

    assert isinstance(provider, provider_class)
    assert provider.model == "remote-model"
    assert provider.dimension == 1024
    assert provider.base_url == "https://embeddings.example/v1"
    assert provider.api_key == "test-key"
    assert provider.batch_size == 2


@pytest.mark.parametrize("name", ["sentence-transformers", "sentence_transformers"])
def test_removed_provider_is_unavailable(name: str) -> None:
    assert name not in EmbeddingProviderFactory.list_providers()
    with pytest.raises(ValueError, match="Unknown provider"):
        EmbeddingProviderFactory.create(provider=name)

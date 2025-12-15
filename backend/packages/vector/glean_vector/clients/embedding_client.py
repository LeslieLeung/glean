"""Embedding client with factory pattern support."""

from typing import Any

from .embedding_factory import EmbeddingProviderFactory
from .providers import EmbeddingProvider
from .rate_limiter import RateLimiter


class EmbeddingClient:
    """
    High-level embedding client.

    Uses factory pattern to support multiple providers.
    Provides a simple interface for embedding generation.

    Example:
        >>> # Use default config
        >>> client = EmbeddingClient()
        >>> embedding, metadata = await client.generate_embedding("Hello world")

        >>> # Override provider
        >>> client = EmbeddingClient(provider="openai", api_key="sk-...")
        >>> embeddings, metadata = await client.generate_embeddings_batch(texts)

        >>> # Use custom config
        >>> from glean_vector.config import EmbeddingConfig
        >>> config = EmbeddingConfig(provider="sentence-transformers", model="all-mpnet-base-v2")
        >>> client = EmbeddingClient(config=config)
    """

    def __init__(
        self,
        provider: str | None = None,
        rate_limit: int | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Initialize embedding client.

        Args:
            provider: Provider name (optional, uses config if None)
            **kwargs: Provider-specific configuration
        """
        self._provider: EmbeddingProvider = EmbeddingProviderFactory.create(
            provider=provider, **kwargs
        )
        self._limiter = RateLimiter(rate_limit) if rate_limit else None

    async def generate_embedding(self, text: str) -> tuple[list[float], dict[str, Any]]:
        """
        Generate embedding for a single text.

        Args:
            text: Input text

        Returns:
            Tuple of (embedding vector, metadata)

        Example:
            >>> client = EmbeddingClient()
            >>> embedding, metadata = await client.generate_embedding("Hello world")
            >>> print(f"Dimension: {len(embedding)}")
            >>> print(f"Model: {metadata['model']}")
        """
        if self._limiter:
            await self._limiter.acquire()
        return await self._provider.generate_embedding(text)

    async def generate_embeddings_batch(
        self, texts: list[str]
    ) -> tuple[list[list[float]], dict[str, Any]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of input texts

        Returns:
            Tuple of (list of embeddings, metadata)

        Example:
            >>> client = EmbeddingClient()
            >>> texts = ["Hello", "World", "AI"]
            >>> embeddings, metadata = await client.generate_embeddings_batch(texts)
            >>> print(f"Generated {len(embeddings)} embeddings")
        """
        if self._limiter:
            await self._limiter.acquire()
        return await self._provider.generate_embeddings_batch(texts)

    async def close(self) -> None:
        """Close client and clean up resources."""
        await self._provider.close()

    async def __aenter__(self) -> "EmbeddingClient":
        """Context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Context manager exit."""
        await self.close()

    @property
    def model(self) -> str:
        """Get current model name."""
        return self._provider.model

    @property
    def dimension(self) -> int:
        """Get embedding dimension."""
        return self._provider.dimension

    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return self._provider.provider_name

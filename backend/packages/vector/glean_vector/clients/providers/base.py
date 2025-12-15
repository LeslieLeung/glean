"""Base embedding provider interface."""

from abc import ABC, abstractmethod
from typing import Any


class EmbeddingProvider(ABC):
    """
    Abstract base class for embedding providers.

    All embedding providers must implement this interface.
    """

    def __init__(self, model: str, dimension: int, **kwargs: Any) -> None:
        """
        Initialize provider.

        Args:
            model: Model name/identifier
            dimension: Expected embedding dimension
            **kwargs: Provider-specific configuration
        """
        self.model = model
        self.dimension = dimension
        self.config = kwargs

    @abstractmethod
    async def generate_embedding(self, text: str) -> tuple[list[float], dict[str, Any]]:
        """
        Generate embedding for a single text.

        Args:
            text: Input text

        Returns:
            Tuple of (embedding vector, metadata)

        Raises:
            Exception: If generation fails
        """
        pass

    @abstractmethod
    async def generate_embeddings_batch(
        self, texts: list[str]
    ) -> tuple[list[list[float]], dict[str, Any]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of input texts

        Returns:
            Tuple of (list of embeddings, metadata)

        Raises:
            Exception: If generation fails
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources."""
        pass

    def validate_dimension(self, embedding: list[float]) -> bool:
        """
        Validate embedding dimension matches expected.

        Args:
            embedding: Generated embedding vector

        Returns:
            True if dimension matches, False otherwise
        """
        return len(embedding) == self.dimension

    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return self.__class__.__name__.replace("Provider", "").lower()

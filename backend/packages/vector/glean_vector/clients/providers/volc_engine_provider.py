"""Volcengine Ark embedding provider using official SDK."""

from typing import Any

from .base import EmbeddingProvider


class VolcEngineProvider(EmbeddingProvider):
    """
    Volcengine Ark API embedding provider using official SDK.

    Supports Volcengine Ark embedding models via the official volcenginesdkarkruntime SDK.
    API Documentation: https://www.volcengine.com/docs/82379/1298454
    """

    def __init__(self, model: str, dimension: int, **kwargs: Any) -> None:
        """
        Initialize Volcengine provider.

        Args:
            model: Volcengine model endpoint ID
            dimension: Embedding dimension
            **kwargs: Provider configuration
                - api_key: API key (required, or set ARK_API_KEY environment variable)
                - base_url: Custom API base URL (optional)
                - timeout: Request timeout in seconds (default: 30)
                - max_retries: Max retry attempts (default: 3)
                - batch_size: Max texts per batch (default: 4, recommended by Volcengine)
        """
        super().__init__(model, dimension, **kwargs)

        self.api_key = kwargs.get("api_key", "")
        self.base_url = kwargs.get("base_url")
        self.timeout = kwargs.get("timeout", 30)
        self.max_retries = kwargs.get("max_retries", 3)
        self.batch_size = kwargs.get("batch_size", 4)

        self._client = None

    def _get_client(self):
        """Get or create Ark client."""
        if self._client is None:
            try:
                from volcenginesdkarkruntime import Ark

                # Initialize Ark client
                client_kwargs = {}
                if self.api_key:
                    client_kwargs["api_key"] = self.api_key
                if self.base_url:
                    client_kwargs["base_url"] = self.base_url
                if self.timeout:
                    client_kwargs["timeout"] = self.timeout
                if self.max_retries:
                    client_kwargs["max_retries"] = self.max_retries

                self._client = Ark(**client_kwargs)

            except ImportError as e:
                raise ImportError(
                    "volcenginesdkarkruntime is not installed. "
                    "Please install it with: pip install 'volcengine-python-sdk[ark]'"
                ) from e

        return self._client

    async def generate_embedding(self, text: str) -> tuple[list[float], dict[str, Any]]:
        """Generate embedding for a single text."""
        client = self._get_client()

        try:
            # Call embeddings API
            response = client.embeddings.create(model=self.model, input=[text])

            # Extract embedding from first result
            if not response.data or len(response.data) == 0:
                raise ValueError("Empty response from Volcengine Ark API")

            embedding = response.data[0].embedding

            # Validate dimension matches expected
            if not self.validate_dimension(embedding):
                raise ValueError(
                    f"Dimension mismatch: expected {self.dimension}, got {len(embedding)}"
                )

            metadata = {
                "model": response.model,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
                "provider": self.provider_name,
                "dimension": len(embedding),
            }

            return embedding, metadata

        except ImportError:
            raise
        except Exception as e:
            raise ValueError(f"Volcengine Ark API error: {str(e)}") from e

    async def generate_embeddings_batch(
        self, texts: list[str]
    ) -> tuple[list[list[float]], dict[str, Any]]:
        """Generate embeddings for multiple texts."""
        if len(texts) > self.batch_size:
            raise ValueError(
                f"Batch size {len(texts)} exceeds limit {self.batch_size}. "
                f"Volcengine recommends batch size <= 4 for optimal performance."
            )

        client = self._get_client()

        try:
            # Call embeddings API with batch
            response = client.embeddings.create(model=self.model, input=texts)

            # Extract embeddings from response
            if not response.data or len(response.data) == 0:
                raise ValueError("Empty response from Volcengine Ark API")

            # Sort by index to maintain order
            sorted_data = sorted(response.data, key=lambda x: x.index)
            embeddings = [item.embedding for item in sorted_data]

            # Validate dimensions match expected
            for i, emb in enumerate(embeddings):
                if not self.validate_dimension(emb):
                    raise ValueError(
                        f"Dimension mismatch at index {i}: expected {self.dimension}, got {len(emb)}"
                    )

            metadata = {
                "model": response.model,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
                "provider": self.provider_name,
                "count": len(texts),
                "dimension": len(embeddings[0]) if embeddings else 0,
            }

            return embeddings, metadata

        except ImportError:
            raise
        except Exception as e:
            raise ValueError(f"Volcengine Ark API error: {str(e)}") from e

    async def close(self) -> None:
        """Close the Ark client."""
        if self._client is not None:
            # Ark client doesn't have explicit close method
            # Resources will be cleaned up automatically
            self._client = None

    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return "volc_engine"

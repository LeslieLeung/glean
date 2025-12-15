"""OpenAI embedding provider."""

import asyncio
from typing import Any

import httpx
from openai import AsyncOpenAI, OpenAIError

from .base import EmbeddingProvider


class OpenAIProvider(EmbeddingProvider):
    """
    OpenAI API embedding provider.

    Supports OpenAI and compatible APIs (e.g., Azure OpenAI, local LiteLLM).
    """

    def __init__(self, model: str, dimension: int, **kwargs: Any) -> None:
        """
        Initialize OpenAI provider.

        Args:
            model: OpenAI model name
            dimension: Embedding dimension
            **kwargs: OpenAI client configuration
                - api_key: API key
                - base_url: Custom API base URL
                - timeout: Request timeout
                - max_retries: Max retry attempts
                - batch_size: Max texts per batch
        """
        super().__init__(model, dimension, **kwargs)

        self.api_key = kwargs.get("api_key", "")
        self.base_url = kwargs.get("base_url")
        self.timeout = kwargs.get("timeout", 30)
        self.max_retries = kwargs.get("max_retries", 3)
        self.batch_size = kwargs.get("batch_size", 20)

        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        """Get or create OpenAI client."""
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout, connect=10.0),
                max_retries=0,  # We handle retries manually
            )
        return self._client

    async def generate_embedding(self, text: str) -> tuple[list[float], dict[str, Any]]:
        """Generate embedding for a single text."""
        return await self._generate_with_retry(text)

    async def _generate_with_retry(
        self, text: str, retry_count: int = 0
    ) -> tuple[list[float], dict[str, Any]]:
        """Generate embedding with retry logic."""
        client = self._get_client()

        try:
            response = await client.embeddings.create(
                input=text, model=self.model, encoding_format="float"
            )

            embedding = response.data[0].embedding

            metadata = {
                "model": response.model,
                "total_tokens": response.usage.total_tokens,
                "provider": self.provider_name,
                "dimension": len(embedding),  # Include actual dimension in metadata
            }

            return embedding, metadata

        except OpenAIError as e:
            # Retry with exponential backoff
            if retry_count < self.max_retries:
                wait_time = 2**retry_count  # 1s, 2s, 4s
                await asyncio.sleep(wait_time)
                return await self._generate_with_retry(text, retry_count + 1)
            raise

    async def generate_embeddings_batch(
        self, texts: list[str]
    ) -> tuple[list[list[float]], dict[str, Any]]:
        """Generate embeddings for multiple texts."""
        if len(texts) > self.batch_size:
            raise ValueError(
                f"Batch size {len(texts)} exceeds limit {self.batch_size}"
            )

        return await self._generate_batch_with_retry(texts)

    async def _generate_batch_with_retry(
        self, texts: list[str], retry_count: int = 0
    ) -> tuple[list[list[float]], dict[str, Any]]:
        """Generate embeddings with retry logic."""
        client = self._get_client()

        try:
            response = await client.embeddings.create(
                input=texts, model=self.model, encoding_format="float"
            )

            # Extract embeddings in original order
            embeddings = [item.embedding for item in response.data]

            metadata = {
                "model": response.model,
                "total_tokens": response.usage.total_tokens,
                "provider": self.provider_name,
                "count": len(texts),
                "dimension": len(embeddings[0]) if embeddings else 0,  # Include actual dimension
            }

            return embeddings, metadata

        except OpenAIError as e:
            # Retry with exponential backoff
            if retry_count < self.max_retries:
                wait_time = 2**retry_count
                await asyncio.sleep(wait_time)
                return await self._generate_batch_with_retry(texts, retry_count + 1)
            raise

    async def close(self) -> None:
        """Close the OpenAI client."""
        if self._client is not None:
            await self._client.close()
            self._client = None

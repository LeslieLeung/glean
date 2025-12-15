"""Factory for creating embedding providers."""

from typing import Any

from glean_vector.config import EmbeddingConfig

from .providers import (
    EmbeddingProvider,
    OpenAIProvider,
    SentenceTransformerProvider,
    VolcEngineProvider,
)


class EmbeddingProviderFactory:
    """
    Factory for creating embedding providers.

    Supports multiple providers with automatic configuration.
    """

    # Registry of available providers
    _PROVIDERS = {
        "openai": OpenAIProvider,
        "sentence-transformers": SentenceTransformerProvider,
        "sentence_transformers": SentenceTransformerProvider,  # Alias
        "volc-engine": VolcEngineProvider,
        "volc_engine": VolcEngineProvider,  # Alias
        "volcengine": VolcEngineProvider,  # Alias
    }

    @classmethod
    def create(
        cls, provider: str | None = None, config: EmbeddingConfig | None = None, **kwargs: Any
    ) -> EmbeddingProvider:
        """
        Create an embedding provider.

        Args:
            provider: Provider name (e.g., 'openai', 'sentence-transformers')
                     If None, reads from config
            config: Embedding configuration. If None, uses global config
            **kwargs: Additional provider-specific configuration
                     Overrides config values

        Returns:
            Configured embedding provider

        Raises:
            ValueError: If provider is unknown or configuration is invalid

        Example:
            >>> # Use global config
            >>> provider = EmbeddingProviderFactory.create()

            >>> # Override provider
            >>> provider = EmbeddingProviderFactory.create(
            ...     provider="openai",
            ...     api_key="sk-...",
            ...     model="text-embedding-3-small"
            ... )

            >>> # Custom configuration
            >>> from glean_vector.config import EmbeddingConfig
            >>> custom_config = EmbeddingConfig(
            ...     provider="sentence-transformers",
            ...     model="all-mpnet-base-v2",
            ...     dimension=768
            ... )
            >>> provider = EmbeddingProviderFactory.create(config=custom_config)
        """
        # Use provided config or global config
        if config is None:
            from glean_vector.config import embedding_config

            config = embedding_config

        # Use provided provider or config provider
        provider_name = (provider or config.provider).lower()

        # Get provider class
        provider_class = cls._PROVIDERS.get(provider_name)
        if provider_class is None:
            available = ", ".join(cls._PROVIDERS.keys())
            raise ValueError(
                f"Unknown provider: {provider_name}. Available providers: {available}"
            )

        # Merge configuration
        provider_config = cls._build_provider_config(provider_name, config, kwargs)

        # Create provider instance
        return provider_class(**provider_config)

    @classmethod
    def _build_provider_config(
        cls, provider: str, config: EmbeddingConfig, overrides: dict[str, Any]
    ) -> dict[str, Any]:
        """Build provider configuration from config and overrides."""
        base_config = {
            "model": config.model,
            "dimension": config.dimension,
        }

        # Add provider-specific config
        if provider in ("openai",):
            base_config.update(
                {
                    "api_key": config.api_key,
                    "base_url": config.base_url,
                    "timeout": config.timeout,
                    "max_retries": config.max_retries,
                    "batch_size": config.batch_size,
                }
            )
        elif provider in ("volc-engine", "volc_engine", "volcengine"):
            base_config.update(
                {
                    "api_key": config.api_key,
                    "base_url": config.base_url,
                    "timeout": config.timeout,
                    "max_retries": config.max_retries,
                    "batch_size": config.batch_size,
                }
            )
        elif provider in ("sentence-transformers", "sentence_transformers"):
            base_config.update(
                {
                    "device": None,  # Auto-detect
                    "normalize_embeddings": True,
                    "batch_size": config.batch_size,
                }
            )

        # Apply overrides
        base_config.update(overrides)

        return base_config

    @classmethod
    def register_provider(
        cls, name: str, provider_class: type[EmbeddingProvider]
    ) -> None:
        """
        Register a custom provider.

        Args:
            name: Provider name
            provider_class: Provider class (must inherit from EmbeddingProvider)

        Example:
            >>> class CustomProvider(EmbeddingProvider):
            ...     pass
            >>> EmbeddingProviderFactory.register_provider("custom", CustomProvider)
        """
        if not issubclass(provider_class, EmbeddingProvider):
            raise TypeError(
                f"Provider class must inherit from EmbeddingProvider, "
                f"got {provider_class.__name__}"
            )

        cls._PROVIDERS[name.lower()] = provider_class

    @classmethod
    def list_providers(cls) -> list[str]:
        """Get list of available provider names."""
        return list(cls._PROVIDERS.keys())

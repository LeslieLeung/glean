"""
Typed configuration schemas.

Defines Pydantic models for system configuration with built-in namespace constants.
Each config class carries its NAMESPACE as a class constant for database storage.
"""

from datetime import datetime
from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel, Field


class VectorizationStatus(str, Enum):
    """Vectorization system status."""

    DISABLED = "disabled"  # Not enabled
    IDLE = "idle"  # Enabled, normal operation
    VALIDATING = "validating"  # Testing provider connection
    REBUILDING = "rebuilding"  # Full re-embedding in progress
    ERROR = "error"  # Provider/Milvus unavailable


class RateLimitConfig(BaseModel):
    """Rate limit configuration for embedding providers."""

    default: int = Field(10, ge=0, le=1000)  # Default rate limit (requests per minute)
    providers: dict[str, int] = Field(default_factory=dict)  # Per-provider overrides


class EmbeddingConfig(BaseModel):
    """
    Embedding system configuration.

    Stored in system_configs table with key = NAMESPACE.
    """

    NAMESPACE: ClassVar[str] = "embedding"

    # Master switch
    enabled: bool = False

    # Provider settings
    provider: str = "openai"
    model: str = "text-embedding-3-small"
    dimension: int = Field(1536, gt=0, le=10000)
    api_key: str | None = None
    base_url: str | None = None
    timeout: int = Field(default=30, gt=0, le=300)
    batch_size: int = Field(default=20, gt=0, le=1000)
    max_retries: int = Field(default=3, ge=0, le=10)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)  # type: ignore[arg-type]

    # System state
    status: VectorizationStatus = VectorizationStatus.DISABLED
    version: str | None = None  # Config version (UUID, changes on update)
    last_error: str | None = None
    last_error_at: datetime | None = None
    error_count: int = 0

    # Rebuild tracking
    rebuild_id: str | None = None
    rebuild_started_at: datetime | None = None

    def get_rate_limit_for_provider(self) -> int:
        """Get rate limit for the current provider."""
        return self.rate_limit.providers.get(self.provider, self.rate_limit.default)


class PreferenceConfig(BaseModel):
    """
    Preference calculation configuration.

    Stored in system_configs table with key = NAMESPACE.
    """

    NAMESPACE: ClassVar[str] = "preference"

    default_score: float = 50.0
    confidence_threshold: int = 10
    like_weight: float = 1.0
    dislike_weight: float = -1.0
    bookmark_weight: float = 0.7
    source_boost_max: float = 5.0
    author_boost_max: float = 3.0


class ScoreConfig(BaseModel):
    """
    Score calculation configuration.

    Stored in system_configs table with key = NAMESPACE.
    """

    NAMESPACE: ClassVar[str] = "score"

    recommend_threshold: float = 70.0
    low_interest_threshold: float = 40.0
    cache_ttl: int = 3600


class EmbeddingRebuildProgress(BaseModel):
    """Embedding rebuild progress tracking."""

    total: int = 0
    pending: int = 0
    processing: int = 0
    done: int = 0
    failed: int = 0


class VectorizationStatusResponse(BaseModel):
    """Response schema for vectorization status endpoint."""

    enabled: bool
    status: VectorizationStatus
    has_error: bool
    error_message: str | None = None
    rebuild_progress: EmbeddingRebuildProgress | None = None


class EmbeddingConfigResponse(BaseModel):
    """Response schema for embedding config (with sensitive fields masked)."""

    enabled: bool
    provider: str
    model: str
    dimension: int
    api_key_set: bool  # Whether API key is configured (masked)
    base_url: str | None
    rate_limit: RateLimitConfig
    status: VectorizationStatus
    version: str | None
    last_error: str | None
    last_error_at: datetime | None
    error_count: int
    rebuild_id: str | None
    rebuild_started_at: datetime | None

    @classmethod
    def from_config(cls, config: EmbeddingConfig) -> "EmbeddingConfigResponse":
        """Create response from config, masking sensitive fields."""
        return cls(
            enabled=config.enabled,
            provider=config.provider,
            model=config.model,
            dimension=config.dimension,
            api_key_set=bool(config.api_key),
            base_url=config.base_url,
            rate_limit=config.rate_limit,
            status=config.status,
            version=config.version,
            last_error=config.last_error,
            last_error_at=config.last_error_at,
            error_count=config.error_count,
            rebuild_id=config.rebuild_id,
            rebuild_started_at=config.rebuild_started_at,
        )


class EmbeddingConfigUpdateRequest(BaseModel):
    """
    Request schema for updating embedding config.

    Note: dimension is optional and will be auto-inferred from the provider
    during validation if not provided.
    """

    enabled: bool | None = None
    provider: str | None = None
    model: str | None = None
    dimension: int | None = Field(None, gt=0, le=10000)  # Optional: auto-inferred if not provided
    api_key: str | None = None
    base_url: str | None = None
    timeout: int | None = Field(None, gt=0, le=300)
    batch_size: int | None = Field(None, gt=0, le=1000)
    max_retries: int | None = Field(None, ge=0, le=10)
    rate_limit: RateLimitConfig | None = None


class ValidationResult(BaseModel):
    """Result of provider/Milvus validation."""

    success: bool
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class RegistrationConfig(BaseModel):
    """
    User registration configuration.

    Stored in system_configs table with key = NAMESPACE.
    """

    NAMESPACE: ClassVar[str] = "registration"

    enabled: bool = True  # Registration enabled by default

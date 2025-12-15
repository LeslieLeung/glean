"""
Tests for configuration validation.

Ensures that invalid configuration values are rejected properly.
"""

import pytest
from pydantic import ValidationError

from glean_core.schemas.config import (
    EmbeddingConfig,
    EmbeddingConfigUpdateRequest,
    RateLimitConfig,
)


class TestRateLimitConfigValidation:
    """Test rate limit configuration validation."""

    def test_valid_default_rate_limit(self):
        """Valid default rate limit should be accepted."""
        config = RateLimitConfig(default=10)
        assert config.default == 10

    def test_rate_limit_minimum(self):
        """Rate limit at minimum boundary (0) should be accepted."""
        config = RateLimitConfig(default=0)
        assert config.default == 0

    def test_rate_limit_maximum(self):
        """Rate limit at maximum boundary (1000) should be accepted."""
        config = RateLimitConfig(default=1000)
        assert config.default == 1000

    def test_negative_rate_limit(self):
        """Negative rate limit should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RateLimitConfig(default=-1)
        assert "greater than or equal to 0" in str(exc_info.value)

    def test_excessive_rate_limit(self):
        """Rate limit above maximum should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RateLimitConfig(default=1001)
        assert "less than or equal to 1000" in str(exc_info.value)


class TestEmbeddingConfigValidation:
    """Test embedding configuration validation."""

    def test_valid_config(self):
        """Valid configuration should be accepted."""
        config = EmbeddingConfig(
            dimension=1536,
            timeout=30,
            batch_size=20,
            max_retries=3,
        )
        assert config.dimension == 1536
        assert config.timeout == 30
        assert config.batch_size == 20
        assert config.max_retries == 3

    def test_zero_dimension(self):
        """Dimension of 0 should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EmbeddingConfig(dimension=0)
        assert "greater than 0" in str(exc_info.value)

    def test_negative_dimension(self):
        """Negative dimension should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EmbeddingConfig(dimension=-100)
        assert "greater than 0" in str(exc_info.value)

    def test_excessive_dimension(self):
        """Dimension above maximum should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EmbeddingConfig(dimension=10001)
        assert "less than or equal to 10000" in str(exc_info.value)

    def test_zero_timeout(self):
        """Timeout of 0 should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EmbeddingConfig(timeout=0)
        assert "greater than 0" in str(exc_info.value)

    def test_negative_timeout(self):
        """Negative timeout should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EmbeddingConfig(timeout=-10)
        assert "greater than 0" in str(exc_info.value)

    def test_excessive_timeout(self):
        """Timeout above maximum should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EmbeddingConfig(timeout=301)
        assert "less than or equal to 300" in str(exc_info.value)

    def test_zero_batch_size(self):
        """Batch size of 0 should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EmbeddingConfig(batch_size=0)
        assert "greater than 0" in str(exc_info.value)

    def test_negative_batch_size(self):
        """Negative batch size should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EmbeddingConfig(batch_size=-5)
        assert "greater than 0" in str(exc_info.value)

    def test_excessive_batch_size(self):
        """Batch size above maximum should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EmbeddingConfig(batch_size=1001)
        assert "less than or equal to 1000" in str(exc_info.value)

    def test_negative_max_retries(self):
        """Negative max retries should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EmbeddingConfig(max_retries=-1)
        assert "greater than or equal to 0" in str(exc_info.value)

    def test_excessive_max_retries(self):
        """Max retries above maximum should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EmbeddingConfig(max_retries=11)
        assert "less than or equal to 10" in str(exc_info.value)

    def test_max_retries_zero(self):
        """Max retries of 0 should be accepted."""
        config = EmbeddingConfig(max_retries=0)
        assert config.max_retries == 0


class TestEmbeddingConfigUpdateRequestValidation:
    """Test embedding configuration update request validation."""

    def test_valid_update_request(self):
        """Valid update request should be accepted."""
        request = EmbeddingConfigUpdateRequest(
            dimension=768,
            timeout=60,
            batch_size=50,
            max_retries=5,
        )
        assert request.dimension == 768
        assert request.timeout == 60
        assert request.batch_size == 50
        assert request.max_retries == 5

    def test_none_values_accepted(self):
        """None values should be accepted (optional fields)."""
        request = EmbeddingConfigUpdateRequest(
            dimension=None,
            timeout=None,
            batch_size=None,
            max_retries=None,
        )
        assert request.dimension is None
        assert request.timeout is None
        assert request.batch_size is None
        assert request.max_retries is None

    def test_zero_dimension_update(self):
        """Dimension of 0 in update should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EmbeddingConfigUpdateRequest(dimension=0)
        assert "greater than 0" in str(exc_info.value)

    def test_negative_dimension_update(self):
        """Negative dimension in update should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EmbeddingConfigUpdateRequest(dimension=-1536)
        assert "greater than 0" in str(exc_info.value)

    def test_excessive_dimension_update(self):
        """Dimension above maximum in update should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EmbeddingConfigUpdateRequest(dimension=20000)
        assert "less than or equal to 10000" in str(exc_info.value)

    def test_zero_timeout_update(self):
        """Timeout of 0 in update should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EmbeddingConfigUpdateRequest(timeout=0)
        assert "greater than 0" in str(exc_info.value)

    def test_negative_timeout_update(self):
        """Negative timeout in update should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EmbeddingConfigUpdateRequest(timeout=-30)
        assert "greater than 0" in str(exc_info.value)

    def test_excessive_timeout_update(self):
        """Timeout above maximum in update should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EmbeddingConfigUpdateRequest(timeout=500)
        assert "less than or equal to 300" in str(exc_info.value)

    def test_zero_batch_size_update(self):
        """Batch size of 0 in update should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EmbeddingConfigUpdateRequest(batch_size=0)
        assert "greater than 0" in str(exc_info.value)

    def test_negative_batch_size_update(self):
        """Negative batch size in update should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EmbeddingConfigUpdateRequest(batch_size=-20)
        assert "greater than 0" in str(exc_info.value)

    def test_excessive_batch_size_update(self):
        """Batch size above maximum in update should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EmbeddingConfigUpdateRequest(batch_size=2000)
        assert "less than or equal to 1000" in str(exc_info.value)

    def test_negative_max_retries_update(self):
        """Negative max retries in update should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EmbeddingConfigUpdateRequest(max_retries=-3)
        assert "greater than or equal to 0" in str(exc_info.value)

    def test_excessive_max_retries_update(self):
        """Max retries above maximum in update should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EmbeddingConfigUpdateRequest(max_retries=20)
        assert "less than or equal to 10" in str(exc_info.value)

    def test_max_retries_zero_update(self):
        """Max retries of 0 in update should be accepted."""
        request = EmbeddingConfigUpdateRequest(max_retries=0)
        assert request.max_retries == 0

    def test_partial_update_request(self):
        """Partial update request with only some fields should be accepted."""
        request = EmbeddingConfigUpdateRequest(
            dimension=512,
            provider="custom",
        )
        assert request.dimension == 512
        assert request.provider == "custom"
        assert request.timeout is None
        assert request.batch_size is None


class TestBoundaryValues:
    """Test boundary values to ensure they work correctly."""

    def test_dimension_boundaries(self):
        """Test dimension at exact boundaries."""
        # Minimum valid value (1)
        config1 = EmbeddingConfig(dimension=1)
        assert config1.dimension == 1

        # Maximum valid value (10000)
        config2 = EmbeddingConfig(dimension=10000)
        assert config2.dimension == 10000

    def test_timeout_boundaries(self):
        """Test timeout at exact boundaries."""
        # Minimum valid value (1)
        config1 = EmbeddingConfig(timeout=1)
        assert config1.timeout == 1

        # Maximum valid value (300)
        config2 = EmbeddingConfig(timeout=300)
        assert config2.timeout == 300

    def test_batch_size_boundaries(self):
        """Test batch size at exact boundaries."""
        # Minimum valid value (1)
        config1 = EmbeddingConfig(batch_size=1)
        assert config1.batch_size == 1

        # Maximum valid value (1000)
        config2 = EmbeddingConfig(batch_size=1000)
        assert config2.batch_size == 1000

    def test_max_retries_boundaries(self):
        """Test max retries at exact boundaries."""
        # Minimum valid value (0)
        config1 = EmbeddingConfig(max_retries=0)
        assert config1.max_retries == 0

        # Maximum valid value (10)
        config2 = EmbeddingConfig(max_retries=10)
        assert config2.max_retries == 10

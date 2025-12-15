"""
Integration tests for admin embedding configuration validation.

Tests that the API properly rejects invalid configuration values.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestEmbeddingConfigValidation:
    """Test embedding configuration validation at API level."""

    async def test_update_config_with_zero_dimension(
        self, client: AsyncClient, admin_headers: dict[str, str]
    ):
        """Test that dimension of 0 is rejected."""
        response = await client.put(
            "/api/admin/embedding/config",
            json={"dimension": 0},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert "greater than 0" in response.text.lower()

    async def test_update_config_with_negative_dimension(
        self, client: AsyncClient, admin_headers: dict[str, str]
    ):
        """Test that negative dimension is rejected."""
        response = await client.put(
            "/api/admin/embedding/config",
            json={"dimension": -1536},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert "greater than 0" in response.text.lower()

    async def test_update_config_with_excessive_dimension(
        self, client: AsyncClient, admin_headers: dict[str, str]
    ):
        """Test that dimension above maximum is rejected."""
        response = await client.put(
            "/api/admin/embedding/config",
            json={"dimension": 20000},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert "less than or equal to 10000" in response.text.lower()

    async def test_update_config_with_zero_timeout(
        self, client: AsyncClient, admin_headers: dict[str, str]
    ):
        """Test that timeout of 0 is rejected."""
        response = await client.put(
            "/api/admin/embedding/config",
            json={"timeout": 0},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert "greater than 0" in response.text.lower()

    async def test_update_config_with_negative_timeout(
        self, client: AsyncClient, admin_headers: dict[str, str]
    ):
        """Test that negative timeout is rejected."""
        response = await client.put(
            "/api/admin/embedding/config",
            json={"timeout": -30},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert "greater than 0" in response.text.lower()

    async def test_update_config_with_excessive_timeout(
        self, client: AsyncClient, admin_headers: dict[str, str]
    ):
        """Test that timeout above maximum is rejected."""
        response = await client.put(
            "/api/admin/embedding/config",
            json={"timeout": 500},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert "less than or equal to 300" in response.text.lower()

    async def test_update_config_with_zero_batch_size(
        self, client: AsyncClient, admin_headers: dict[str, str]
    ):
        """Test that batch size of 0 is rejected."""
        response = await client.put(
            "/api/admin/embedding/config",
            json={"batch_size": 0},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert "greater than 0" in response.text.lower()

    async def test_update_config_with_negative_batch_size(
        self, client: AsyncClient, admin_headers: dict[str, str]
    ):
        """Test that negative batch size is rejected."""
        response = await client.put(
            "/api/admin/embedding/config",
            json={"batch_size": -20},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert "greater than 0" in response.text.lower()

    async def test_update_config_with_excessive_batch_size(
        self, client: AsyncClient, admin_headers: dict[str, str]
    ):
        """Test that batch size above maximum is rejected."""
        response = await client.put(
            "/api/admin/embedding/config",
            json={"batch_size": 2000},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert "less than or equal to 1000" in response.text.lower()

    async def test_update_config_with_negative_max_retries(
        self, client: AsyncClient, admin_headers: dict[str, str]
    ):
        """Test that negative max retries is rejected."""
        response = await client.put(
            "/api/admin/embedding/config",
            json={"max_retries": -3},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert "greater than or equal to 0" in response.text.lower()

    async def test_update_config_with_excessive_max_retries(
        self, client: AsyncClient, admin_headers: dict[str, str]
    ):
        """Test that max retries above maximum is rejected."""
        response = await client.put(
            "/api/admin/embedding/config",
            json={"max_retries": 20},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert "less than or equal to 10" in response.text.lower()

    async def test_update_config_with_valid_values(
        self, client: AsyncClient, admin_headers: dict[str, str]
    ):
        """Test that valid configuration values are accepted."""
        response = await client.put(
            "/api/admin/embedding/config",
            json={
                "dimension": 768,
                "timeout": 60,
                "batch_size": 50,
                "max_retries": 5,
            },
            headers=admin_headers,
        )
        # Should succeed or fail with a different error (not validation)
        # Note: May fail with 400 if provider validation fails, but not 422
        assert response.status_code in [200, 400]

    async def test_update_config_with_boundary_values(
        self, client: AsyncClient, admin_headers: dict[str, str]
    ):
        """Test that boundary values are accepted."""
        response = await client.put(
            "/api/admin/embedding/config",
            json={
                "dimension": 1,  # Minimum
                "timeout": 1,  # Minimum
                "batch_size": 1,  # Minimum
                "max_retries": 0,  # Minimum
            },
            headers=admin_headers,
        )
        # Should succeed or fail with a different error (not validation)
        assert response.status_code in [200, 400]

        response = await client.put(
            "/api/admin/embedding/config",
            json={
                "dimension": 10000,  # Maximum
                "timeout": 300,  # Maximum
                "batch_size": 1000,  # Maximum
                "max_retries": 10,  # Maximum
            },
            headers=admin_headers,
        )
        # Should succeed or fail with a different error (not validation)
        assert response.status_code in [200, 400]

    async def test_update_config_with_multiple_invalid_values(
        self, client: AsyncClient, admin_headers: dict[str, str]
    ):
        """Test that multiple invalid values are all caught."""
        response = await client.put(
            "/api/admin/embedding/config",
            json={
                "dimension": 0,
                "timeout": -10,
                "batch_size": 2000,
                "max_retries": 50,
            },
            headers=admin_headers,
        )
        assert response.status_code == 422
        # Should report at least one of the errors
        response_text = response.text.lower()
        assert any(
            error in response_text
            for error in [
                "greater than 0",
                "less than or equal to",
                "greater than or equal to",
            ]
        )

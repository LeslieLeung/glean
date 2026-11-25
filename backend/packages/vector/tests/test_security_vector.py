"""Security tests for embedding provider SSRF and validation error sanitization."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from glean_core.schemas.config import EmbeddingConfig
from glean_vector.clients.providers.openai_provider import OpenAIProvider
from glean_vector.clients.providers.ssrf import (
    EmbeddingSSRFError,
    EmbeddingSSRFSafeTransport,
)
from glean_vector.clients.providers.volc_engine_provider import VolcEngineProvider
from glean_vector.services.validation_service import EmbeddingValidationService


class TestEmbeddingSSRF:
    """Tests for OpenAI and Volcengine SSRF protections."""

    @pytest.mark.parametrize(
        "blocked_url",
        [
            "http://169.254.169.254/latest/meta-data",
            "http://metadata.google.internal/v1",
            "http://127.0.0.1:8080/v1",
            "http://10.0.0.1:8000/v1",
            "http://service.default.svc.cluster.local:8080",
            "file:///etc/passwd",
        ],
    )
    def test_openai_provider_rejects_blocked_base_urls(
        self, blocked_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GLEAN_EMBEDDING_ALLOW_PRIVATE", raising=False)
        monkeypatch.delenv("SSRF_ALLOW_PRIVATE", raising=False)
        monkeypatch.delenv("GLEAN_SSRF_ALLOW_PRIVATE", raising=False)
        with pytest.raises(EmbeddingSSRFError):
            OpenAIProvider(model="text-embedding-3-small", dimension=1536, base_url=blocked_url)

    def test_private_override_allows_local_vllm_but_keeps_metadata_blocked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GLEAN_EMBEDDING_ALLOW_PRIVATE", "true")
        provider = OpenAIProvider(
            model="local-model", dimension=384, base_url="http://127.0.0.1:8080/v1"
        )
        assert provider.base_url == "http://127.0.0.1:8080/v1"

        with pytest.raises(EmbeddingSSRFError):
            OpenAIProvider(
                model="local-model",
                dimension=384,
                base_url="http://169.254.169.254/latest/meta-data",
            )

    @pytest.mark.asyncio
    async def test_openai_transport_pins_dns_and_preserves_sni_for_idna(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GLEAN_EMBEDDING_ALLOW_PRIVATE", raising=False)
        monkeypatch.delenv("SSRF_ALLOW_PRIVATE", raising=False)
        monkeypatch.delenv("GLEAN_SSRF_ALLOW_PRIVATE", raising=False)

        captured: list[httpx.Request] = []

        async def mock_inner(req: httpx.Request) -> httpx.Response:
            captured.append(req)
            return httpx.Response(200, json={"ok": True})

        transport = EmbeddingSSRFSafeTransport()
        transport._inner = SimpleNamespace(handle_async_request=mock_inner, aclose=AsyncMock())  # type: ignore[assignment]

        with patch(
            "glean_vector.clients.providers.ssrf.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("93.184.216.34", 443))],
        ):
            req = httpx.Request("POST", "https://api.example.com/v1/embeddings")
            resp = await transport.handle_async_request(req)

        assert resp.status_code == 200
        assert captured[0].url.host == "93.184.216.34"
        assert captured[0].extensions["sni_hostname"] == b"api.example.com"

    @pytest.mark.asyncio
    async def test_volcengine_provider_blocks_dns_rebinding_before_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GLEAN_EMBEDDING_ALLOW_PRIVATE", raising=False)
        monkeypatch.delenv("SSRF_ALLOW_PRIVATE", raising=False)
        monkeypatch.delenv("GLEAN_SSRF_ALLOW_PRIVATE", raising=False)

        provider = VolcEngineProvider(
            model="ep-test",
            dimension=1024,
            api_key="test-key",
            base_url="https://rebinding.example.com",
        )
        with (
            patch(
                "glean_vector.clients.providers.ssrf.socket.getaddrinfo",
                return_value=[(2, 1, 6, "", ("127.0.0.1", 443))],
            ),
            pytest.raises(EmbeddingSSRFError),
        ):
            await provider.generate_embedding("hello")


class TestValidationErrorSanitization:
    """Ensure upstream error payloads are never leaked in ValidationResult."""

    @pytest.mark.asyncio
    async def test_validation_sanitizes_raw_upstream_exception(self) -> None:
        config = EmbeddingConfig(
            enabled=False,
            provider="openai",
            model="text-embedding-3-small",
            dimension=1536,
            api_key="sk-secret",
        )
        failing_provider = SimpleNamespace(
            generate_embedding=AsyncMock(
                side_effect=RuntimeError('HTTP 401 body: {"secret_header": "Bearer sk-secret"}')
            ),
            close=AsyncMock(),
        )
        with patch(
            "glean_vector.clients.embedding_factory.EmbeddingProviderFactory.create",
            return_value=failing_provider,
        ):
            result = await EmbeddingValidationService().validate_provider(config)

        assert result.success is False
        assert "Bearer sk-secret" not in result.message
        assert "Bearer sk-secret" not in str(result.details)
        assert "RuntimeError" in result.message

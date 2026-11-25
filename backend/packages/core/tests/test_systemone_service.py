"""System One provider abstraction, protocol compatibility, and registry tests."""

import json

import httpx
import pytest
from pydantic import ValidationError

from glean_core.schemas.jev import JevConfig
from glean_core.schemas.systemone import (
    ProviderDescriptor,
    ProviderProfile,
    SystemOneConfig,
    SystemOneNoulAnswer,
    normalize_base_url,
)
from glean_core.services import systemone_service
from glean_core.services.systemone_providers import (
    ResolvedConnection,
    SystemOneProvider,
    SystemOneProviderRegistry,
)


@pytest.fixture
def systemone_http(monkeypatch):
    real_client = httpx.AsyncClient
    captured_timeouts: list[object] = []

    def install(handler):
        def factory(**kwargs):
            captured_timeouts.append(kwargs.get("timeout"))
            return real_client(transport=httpx.MockTransport(handler), **kwargs)

        monkeypatch.setattr(systemone_service.httpx, "AsyncClient", factory)
        return captured_timeouts

    return install


async def test_jev_provider_supports_pinned_model_and_records_provider(systemone_http):
    config = SystemOneConfig(
        provider="jev",
        providers={"jev": ProviderProfile(base_url="https://api.typesafe.ai", model="jev-preview")},
        provider_api_keys={"jev": "jev-secret"},
    )

    def handler(request):
        assert request.url == "https://api.typesafe.ai/v1/systemone"
        assert request.headers["Authorization"] == "Bearer jev-secret"
        body = json.loads(request.content)
        assert body["model"] == "jev-preview"
        assert "max_len" not in body
        return httpx.Response(
            200,
            json={
                "model": "jev-preview-2026",
                "answers": {
                    "ai_generated": {"noul": 0.2},
                    "content_type": {"choice": "original", "confidence": 0.9},
                },
            },
        )

    systemone_http(handler)
    result = await systemone_service.classify_text(config, "text", "Title", "https://example.com")
    assert result.provider == "jev"
    assert result.model_id == "jev-preview-2026"
    assert result.label == "human"
    assert result.score == 0.8


async def test_clef_provider_calls_workers_ai_unwraps_result_and_runs_inference_test(
    systemone_http,
):
    account_id = "a" * 32
    config = SystemOneConfig(
        provider="clef",
        providers={"clef": ProviderProfile(account_id=account_id, model="clef")},
        provider_api_keys={"clef": "cf-token", "jev": "unrelated-jev-key"},
    )
    requests = []

    def handler(request):
        requests.append(
            (request.method, str(request.url), dict(request.headers), json.loads(request.content))
        )
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {
                    "model": "clef",
                    "answers": {
                        "ai_generated": {"noul": 0.8},
                        "content_type": {
                            "choice": "ad",
                            "probabilities": {"ad": 0.7, "original": 0.2, "repost": 0.1},
                        },
                    },
                },
            },
        )

    systemone_http(handler)
    result = await systemone_service.classify_text(
        config, "x" * 7000, "Title", "https://example.com"
    )
    assert result.provider == "clef"
    assert result.model_id == "clef"
    assert result.label == "ai"
    assert result.score == 0.8
    assert result.content is not None
    assert result.content.label == "ad"
    assert result.content.confidence == 0.7

    method, url, headers, body = requests[0]
    assert method == "POST"
    assert (
        url
        == f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/cloudflare/clef"
    )
    assert headers["authorization"] == "Bearer cf-token"
    assert body["model"] == "clef"
    assert len(body["state"]["text"]) == 6000
    assert "max_len" not in body

    await systemone_service.test_connection(config)
    assert requests[1][0] == "POST"
    assert requests[1][3]["state"] == {"text": "This is a connection test."}


async def test_clef_rejects_error_envelope_without_leaking_body(systemone_http):
    config = SystemOneConfig(
        provider="clef",
        providers={"clef": ProviderProfile(account_id="a" * 32, model="clef-flash")},
        provider_api_keys={"clef": "cf-token"},
    )
    systemone_http(
        lambda request: httpx.Response(
            200,
            json={"success": False, "errors": [{"message": "sensitive internal detail"}]},
        )
    )
    with pytest.raises(ValueError, match="Clef \\(Cloudflare\\) request failed") as error:
        await systemone_service.classify_text(config, "text", "Title", "https://example.com")
    assert "sensitive" not in str(error.value)


@pytest.mark.parametrize(
    ("profile", "api_key"),
    [
        (ProviderProfile(account_id="short", model="clef-flash"), "cf-token"),
        (ProviderProfile(account_id="z" * 32, model="clef-flash"), "cf-token"),
        (ProviderProfile(account_id="../other", model="clef-flash"), "cf-token"),
        (ProviderProfile(account_id="a" * 32, model="jev-latest"), "cf-token"),
        (ProviderProfile(account_id="a" * 32, model="../evil"), "cf-token"),
        (ProviderProfile(account_id="a" * 32, model="clef-flash"), None),
    ],
)
async def test_clef_invalid_configuration_fails_before_http_request(
    systemone_http, profile, api_key
):
    def fail_if_called(request):
        raise AssertionError("HTTP call must not happen for invalid Clef settings")

    systemone_http(fail_if_called)
    config = SystemOneConfig(
        provider="clef",
        providers={"clef": profile},
        provider_api_keys={"clef": api_key} if api_key else {},
    )
    assert systemone_service.is_configured(config) is False
    with pytest.raises(ValueError):
        await systemone_service.test_connection(config)


async def test_laya_supports_keyless_auth_multilingual_window_and_custom_prefix(systemone_http):
    config = SystemOneConfig(
        provider="laya",
        providers={
            "laya": ProviderProfile(base_url="http://localhost:8000/laya/v1/", model="multilingual")
        },
        provider_api_keys={"jev": "unrelated-key"},
        classify_content=False,
    )
    assert systemone_service.is_configured(config) is True
    captured = []

    def handler(request):
        captured.append((str(request.url), dict(request.headers), json.loads(request.content)))
        return httpx.Response(200, json={"answers": {"ai_generated": {"noul": 0.3}}})

    timeouts = systemone_http(handler)
    result = await systemone_service.classify_text(
        config, "中文文章", "标题", "https://example.com"
    )
    assert result.provider == "laya"
    assert result.model_id == "multilingual"
    assert result.label == "human"
    assert result.score == 0.7
    assert timeouts[0] == 60.0
    assert captured[0][0] == "http://localhost:8000/laya/v1/systemone"
    assert "authorization" not in captured[0][1]
    assert captured[0][2]["max_len"] == 8192

    # Keyed english model omits max_len and sends Authorization header.
    config_english = SystemOneConfig(
        provider="laya",
        providers={"laya": ProviderProfile(base_url="http://localhost:8000", model="english")},
        provider_api_keys={"laya": "laya-secret"},
        classify_content=False,
    )
    await systemone_service.classify_text(
        config_english, "English text", "Title", "https://example.com"
    )
    assert captured[1][1]["authorization"] == "Bearer laya-secret"
    assert captured[1][2]["model"] == "english"
    assert "max_len" not in captured[1][2]


async def test_laya_connection_test_rejects_incomplete_answer(systemone_http):
    config = SystemOneConfig(provider="laya")
    systemone_http(lambda request: httpx.Response(200, json={"answers": {}}))
    with pytest.raises(ValueError):
        await systemone_service.test_connection(config)


async def test_custom_provider_requires_base_url_and_model_and_omits_max_len(systemone_http):
    incomplete = SystemOneConfig(provider="custom")
    assert systemone_service.is_configured(incomplete) is False
    with pytest.raises(ValueError, match="server URL is required"):
        await systemone_service.test_connection(incomplete)

    missing_model = SystemOneConfig(
        provider="custom",
        providers={"custom": ProviderProfile(base_url="https://sys1.example.com")},
    )
    assert systemone_service.is_configured(missing_model) is False
    with pytest.raises(ValueError, match="model is required"):
        await systemone_service.test_connection(missing_model)

    valid = SystemOneConfig(
        provider="custom",
        providers={
            "custom": ProviderProfile(
                base_url="https://sys1.example.com/v1/systemone",
                model="multilingual",
            )
        },
        classify_content=False,
    )
    captured = []

    def handler(request):
        captured.append((str(request.url), json.loads(request.content)))
        return httpx.Response(200, json={"answers": {"ai_generated": {"noul": 0.9}}})

    systemone_http(handler)
    result = await systemone_service.classify_text(valid, "text", "Title", "https://example.com")
    assert result.provider == "custom"
    assert result.model_id == "multilingual"
    assert captured[0][0] == "https://sys1.example.com/v1/systemone"
    assert "max_len" not in captured[0][1]


def test_normalize_base_url_preserves_hostnames_and_prefixes():
    assert normalize_base_url("http://v1/") == "http://v1"
    assert normalize_base_url("https://v1.example.com/v1/models/") == "https://v1.example.com"
    assert normalize_base_url("http://localhost:8000/laya/v1/") == "http://localhost:8000/laya"


@pytest.mark.parametrize("bad_noul", [True, False, -0.1, 1.1, None])
def test_probability_rejects_booleans_and_out_of_range_values(bad_noul):
    with pytest.raises(ValidationError):
        SystemOneNoulAnswer(noul=bad_noul)


def test_legacy_jev_config_migrates_losslessly_and_roundtrips():
    legacy = JevConfig.model_validate(
        {
            "enabled": True,
            "base_url": "https://custom.jev.example/v1/systemone",
            "api_key": "legacy-secret",
            "show_confidence": True,
            "min_text_length": 300,
        }
    )
    assert legacy.provider == "jev"
    assert legacy.base_url == "https://custom.jev.example"
    assert legacy.api_key == "legacy-secret"
    assert legacy.provider_api_keys == {"jev": "legacy-secret"}
    assert not hasattr(legacy, "min_text_length")
    dumped = legacy.model_dump(mode="json")
    assert "show_confidence" not in dumped
    assert "min_text_length" not in dumped
    assert "api_key" not in dumped
    reloaded = SystemOneConfig.model_validate(dumped)
    assert reloaded == legacy


async def test_custom_registered_provider_subclass_works_end_to_end():
    class CustomAcmeProvider(SystemOneProvider):
        descriptor = ProviderDescriptor(
            id="acme",
            name="Acme Decision",
            default_base_url="https://acme.example",
            default_model="acme-v1",
            suggested_models=["acme-v1"],
            requires_api_key=False,
        )

        def inference_url(self, connection: ResolvedConnection) -> str:
            return f"{connection.base_url}/decide"

    registry = SystemOneProviderRegistry()
    registry.register(CustomAcmeProvider())
    provider = registry.get("acme")
    connection = provider.validate_connection(ProviderProfile(), None)

    def handler(request):
        assert request.url == "https://acme.example/decide"
        return httpx.Response(200, json={"answers": {"ai_generated": {"noul": 0.15}}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await provider.classify(
            client,
            connection,
            {"text": "Hello"},
            {"ai_generated": {"type": "noul", "instructions": "AI?"}},
        )
        await provider.test_connection(client, connection)

    assert response.answers.ai_generated.noul == 0.15

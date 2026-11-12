"""Jev protocol compatibility and response validation."""

import json

import httpx
import pytest
from pydantic import ValidationError

from glean_core.schemas.jev import ContentCategory, JevConfig, JevSettings
from glean_core.services import jev_service


@pytest.fixture
def jev_http(monkeypatch):
    real_client = httpx.AsyncClient

    def install(handler):
        monkeypatch.setattr(
            jev_service.httpx,
            "AsyncClient",
            lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
        )

    return install


async def test_custom_prompts_and_categories_use_systemone_protocol(jev_http):
    config = JevConfig(
        api_key="test-secret",
        ai_prompt="Is this AI writing?",
        content_prompt="Choose a topic.",
        categories=[
            ContentCategory(id="science", label="Science", description="Scientific research")
        ],
    )

    def handler(request):
        assert request.url == "https://api.typesafe.ai/v1/systemone"
        assert request.headers["Authorization"] == "Bearer test-secret"
        body = json.loads(request.content)
        assert body["model"] == "jev-latest"
        assert len(body["state"]["text"]) == 6000
        assert body["state"]["title"] == "Article"
        assert body["questions"]["ai_generated"]["instructions"] == "Is this AI writing?"
        assert body["questions"]["content_type"] == {
            "type": "choice",
            "instructions": "Choose a topic.",
            "criteria": {"science": "Science: Scientific research"},
        }
        return httpx.Response(
            200,
            json={
                "model": "jev-test",
                "answers": {
                    "ai_generated": {"noul": 0.1},
                    "content_type": {"choice": "science", "probabilities": {"science": 0.9}},
                },
            },
        )

    jev_http(handler)
    result = await jev_service.classify_text(config, "x" * 8000, "Article", "https://example.com")
    assert result.label == "human"
    assert result.score == 0.9
    assert result.content.name == "Science"
    assert result.content.confidence == 0.9


async def test_ai_only_detection_omits_choice_question(jev_http):
    def handler(request):
        assert "content_type" not in json.loads(request.content)["questions"]
        return httpx.Response(200, json={"answers": {"ai_generated": {"noul": 0.8}}})

    jev_http(handler)
    result = await jev_service.classify_text(
        JevConfig(api_key="test-key", classify_content=False),
        "text",
        "Title",
        "https://example.com",
    )
    assert result.label == "ai"
    assert result.score == 0.8
    assert result.content is None


@pytest.mark.parametrize(
    "answers",
    [
        {},
        {"ai_generated": {"noul": 1.2}},
        {"ai_generated": {"noul": 0.2}},
        {"ai_generated": {"noul": 0.2}, "content_type": {"choice": "unknown", "confidence": 0.9}},
        {"ai_generated": {"noul": 0.2}, "content_type": {"choice": "original"}},
    ],
)
async def test_invalid_or_incomplete_results_are_rejected(jev_http, answers):
    jev_http(lambda request: httpx.Response(200, json={"answers": answers}))
    with pytest.raises(ValueError):
        await jev_service.classify_text(JevConfig(api_key="test-key"), "text", "Title", "url")


async def test_connection_test_uses_models_and_sanitizes_auth_failure(jev_http):
    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/v1/models"
        return httpx.Response(401, text="sensitive upstream diagnostic")

    jev_http(handler)
    with pytest.raises(ValueError, match="authentication failed") as error:
        await jev_service.test_connection(JevConfig(api_key="test-secret"))
    assert "sensitive" not in str(error.value)
    assert "test-secret" not in str(error.value)


def test_article_text_strips_markup_and_non_article_content():
    assert (
        jev_service.article_text(
            "<style>hidden</style><p>Hello &amp; world</p><script>bad()</script>"
        )
        == "Hello & world"
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"base_url": "file:///tmp/key"},
        {"base_url": "https://user:key@example.com"},
        {"categories": []},
        {"min_text_length": 10},
        {"categories": [{"id": "a", "label": "A"}, {"id": "a", "label": "B"}]},
        {"categories": [{"id": "a", "label": "A"}, {"id": "b", "label": "a"}]},
    ],
)
def test_invalid_settings_are_rejected(changes):
    with pytest.raises(ValidationError):
        JevSettings(**changes)


def test_endpoint_urls_are_normalized():
    assert (
        JevSettings(base_url="https://example.com/v1/systemone/").base_url == "https://example.com"
    )

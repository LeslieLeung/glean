"""Jev System One protocol, shared by the admin API and worker."""

from typing import Any

import httpx
from bs4 import BeautifulSoup

from glean_core.schemas.jev import (
    ContentClassification,
    EntryClassification,
    JevConfig,
    JevResponse,
    JevSettings,
)

TEXT_BUDGET = 6000


def build_questions(config: JevSettings) -> dict[str, Any]:
    questions: dict[str, Any] = {
        "ai_generated": {
            "type": "noul",
            "instructions": config.ai_prompt,
            "criteria": {
                "true": "The text was written by an AI language model.",
                "false": "The text was written by a human.",
            },
        }
    }
    if config.classify_content:
        questions["content_type"] = {
            "type": "choice",
            "instructions": config.content_prompt,
            "criteria": {
                item.id: f"{item.label}: {item.description}" if item.description else item.label
                for item in config.categories
            },
        }
    return questions


def article_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "noscript"]):
        element.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())[:TEXT_BUDGET]


def _headers(config: JevConfig) -> dict[str, str]:
    if not config.api_key:
        raise ValueError("Jev API key is required")
    return {"Authorization": f"Bearer {config.api_key}"}


def _check_response(response: httpx.Response) -> None:
    if response.status_code in {401, 403}:
        raise ValueError("Jev authentication failed. Check the API key.")
    if not response.is_success:
        # Do not expose upstream bodies or request headers containing credentials.
        raise ValueError(f"Jev request failed (HTTP {response.status_code})")


async def test_connection(config: JevConfig) -> None:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(f"{config.base_url}/v1/models", headers=_headers(config))
        _check_response(response)


async def classify_text(config: JevConfig, text: str, title: str, url: str) -> EntryClassification:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{config.base_url}/v1/systemone",
            headers=_headers(config),
            json={
                "model": "jev-latest",
                "state": {"text": text[:TEXT_BUDGET], "title": title, "url": url},
                "questions": build_questions(config),
            },
        )
        _check_response(response)
        data = JevResponse.model_validate(response.json())
    probability = data.answers.ai_generated.noul
    content = None
    if config.classify_content:
        choice = data.answers.content_type
        if choice is None:
            raise ValueError("Jev did not return a content classification")
        category = next((item for item in config.categories if item.id == choice.choice), None)
        if category is None:
            raise ValueError("Jev returned an unknown content category")
        assert choice.confidence is not None
        content = ContentClassification(
            label=category.id, name=category.label, confidence=choice.confidence
        )
    return EntryClassification(
        label="ai" if probability >= 0.5 else "human",
        score=probability if probability >= 0.5 else 1 - probability,
        model_id=data.model,
        content=content,
    )


def classification_for_display(
    raw: dict[str, Any] | None, config: JevConfig
) -> EntryClassification | None:
    if not config.enabled or not raw:
        return None
    result = EntryClassification.model_validate(raw)
    return result.model_copy(
        update={
            "show_confidence": config.show_confidence,
            "content": result.content if config.classify_content else None,
        }
    )

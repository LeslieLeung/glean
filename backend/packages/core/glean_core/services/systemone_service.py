"""System One classification service, shared by the admin API and worker."""

from typing import Any

import httpx
from bs4 import BeautifulSoup

from glean_core.schemas.systemone import (
    ContentClassification,
    EntryClassification,
    SystemOneConfig,
    SystemOneSettings,
)
from glean_core.services.systemone_providers import (
    ResolvedConnection,
    SystemOneProvider,
    get_provider,
)

TEXT_BUDGET = 6000


def build_questions(config: SystemOneSettings) -> dict[str, Any]:
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


def resolve_connection(
    config: SystemOneConfig, *, require_credentials: bool = True
) -> tuple[SystemOneProvider, ResolvedConnection]:
    provider = get_provider(config.provider)
    connection = provider.validate_connection(
        config.active_profile,
        config.api_key,
        require_credentials=require_credentials,
    )
    return provider, connection


def is_configured(config: SystemOneConfig) -> bool:
    try:
        resolve_connection(config, require_credentials=True)
    except ValueError:
        return False
    return True


async def test_connection(config: SystemOneConfig) -> None:
    provider, connection = resolve_connection(config, require_credentials=True)
    async with httpx.AsyncClient(timeout=provider.test_timeout) as client:
        await provider.test_connection(client, connection)


async def classify_text(
    config: SystemOneConfig, text: str, title: str, url: str
) -> EntryClassification:
    provider, connection = resolve_connection(config, require_credentials=True)
    async with httpx.AsyncClient(timeout=provider.timeout) as client:
        data = await provider.classify(
            client,
            connection,
            {"text": text[:TEXT_BUDGET], "title": title, "url": url},
            build_questions(config),
        )
    probability = data.answers.ai_generated.noul
    content = None
    if config.classify_content:
        choice = data.answers.content_type
        if choice is None:
            raise ValueError(f"{provider.descriptor.name} did not return a content classification")
        category = next((item for item in config.categories if item.id == choice.choice), None)
        if category is None:
            raise ValueError(f"{provider.descriptor.name} returned an unknown content category")
        assert choice.confidence is not None
        content = ContentClassification(
            label=category.id, name=category.label, confidence=choice.confidence
        )
    return EntryClassification(
        label="ai" if probability >= 0.5 else "human",
        score=probability if probability >= 0.5 else 1 - probability,
        model_id=data.model or connection.model,
        provider=connection.provider,
        content=content,
    )


def classification_for_display(
    raw: dict[str, Any] | None, config: SystemOneSettings
) -> EntryClassification | None:
    if not config.enabled or not raw:
        return None
    result = EntryClassification.model_validate(raw)
    return result if config.classify_content else result.model_copy(update={"content": None})

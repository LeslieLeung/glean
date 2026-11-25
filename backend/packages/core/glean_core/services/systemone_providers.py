"""Pluggable System One decision-model providers and registry."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, cast

import httpx

from glean_core.schemas.systemone import (
    CLOUDFLARE_ACCOUNT_ID_PATTERN,
    PROVIDER_DESCRIPTOR_MAP,
    ProviderDescriptor,
    ProviderProfile,
    SystemOneResponse,
    normalize_base_url,
    set_provider_descriptor_source,
)


@dataclass(frozen=True)
class ResolvedConnection:
    """Validated runtime connection parameters for a System One provider."""

    provider: str
    model: str
    base_url: str | None = None
    account_id: str | None = None
    api_key: str | None = None


class SystemOneProvider(ABC):
    """Base adapter for a System One compatible decision-model provider."""

    descriptor: ProviderDescriptor
    timeout: float = 30.0
    test_timeout: float = 30.0

    def validate_connection(
        self,
        profile: ProviderProfile,
        api_key: str | None,
        *,
        require_credentials: bool = True,
    ) -> ResolvedConnection:
        base_url: str | None = None
        if self.descriptor.uses_base_url:
            raw_url = (
                profile.base_url
                if profile.base_url is not None
                else self.descriptor.default_base_url
            )
            if not raw_url:
                raise ValueError(f"{self.descriptor.name} server URL is required")
            base_url = normalize_base_url(raw_url)

        account_id: str | None = None
        if self.descriptor.uses_account_id:
            candidate_id = profile.account_id.strip() if profile.account_id else ""
            if not CLOUDFLARE_ACCOUNT_ID_PATTERN.fullmatch(candidate_id):
                raise ValueError("Enter a valid 32-character Cloudflare account ID")
            account_id = candidate_id

        model = profile.model.strip() if profile.model else (self.descriptor.default_model or "")
        if not model:
            raise ValueError(f"{self.descriptor.name} model is required")
        if not self.descriptor.allow_custom_model and model not in self.descriptor.suggested_models:
            if self.descriptor.id == "clef":
                raise ValueError("Choose clef or clef-flash")
            raise ValueError(f"Unsupported model for {self.descriptor.name}: {model}")

        cleaned_key = api_key.strip() if api_key else None
        if require_credentials and self.descriptor.requires_api_key and not cleaned_key:
            raise ValueError(f"{self.descriptor.name} API key is required")

        return ResolvedConnection(
            provider=self.descriptor.id,
            model=model,
            base_url=base_url,
            account_id=account_id,
            api_key=cleaned_key or None,
        )

    @abstractmethod
    def inference_url(self, connection: ResolvedConnection) -> str:
        """Return the inference POST URL for a validated connection."""

    def build_headers(self, connection: ResolvedConnection) -> dict[str, str]:
        if not connection.api_key:
            return {}
        return {"Authorization": f"Bearer {connection.api_key}"}

    def build_request_body(
        self,
        connection: ResolvedConnection,
        state: dict[str, Any],
        questions: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "model": connection.model,
            "state": state,
            "questions": questions,
        }

    def check_response(self, response: httpx.Response) -> None:
        if response.status_code in {401, 403}:
            raise ValueError(f"{self.descriptor.name} authentication failed. Check the API key.")
        if not response.is_success:
            # Do not expose upstream bodies or request headers containing credentials.
            raise ValueError(f"{self.descriptor.name} request failed (HTTP {response.status_code})")

    def parse_json(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise ValueError(f"{self.descriptor.name} returned an invalid JSON response") from exc

    def unwrap_response(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError(f"{self.descriptor.name} returned an unexpected response format")
        return cast(dict[str, Any], payload)

    async def classify(
        self,
        client: httpx.AsyncClient,
        connection: ResolvedConnection,
        state: dict[str, Any],
        questions: dict[str, Any],
    ) -> SystemOneResponse:
        response = await client.post(
            self.inference_url(connection),
            headers=self.build_headers(connection),
            json=self.build_request_body(connection, state, questions),
        )
        self.check_response(response)
        payload = self.unwrap_response(self.parse_json(response))
        return SystemOneResponse.model_validate(payload)

    async def test_connection(
        self,
        client: httpx.AsyncClient,
        connection: ResolvedConnection,
    ) -> None:
        await self.classify(
            client,
            connection,
            {"text": "This is a connection test."},
            {
                "ai_generated": {
                    "type": "noul",
                    "instructions": "Does the text describe a connection test?",
                }
            },
        )


class JevProvider(SystemOneProvider):
    """TypeSafe Jev System One provider."""

    descriptor = PROVIDER_DESCRIPTOR_MAP["jev"]
    timeout = 30.0
    test_timeout = 15.0

    def inference_url(self, connection: ResolvedConnection) -> str:
        return f"{connection.base_url}/v1/systemone"

    async def test_connection(
        self,
        client: httpx.AsyncClient,
        connection: ResolvedConnection,
    ) -> None:
        response = await client.get(
            f"{connection.base_url}/v1/models",
            headers=self.build_headers(connection),
        )
        self.check_response(response)


class ClefProvider(SystemOneProvider):
    """Cloudflare Workers AI Clef / Clef-flash provider."""

    descriptor = PROVIDER_DESCRIPTOR_MAP["clef"]
    timeout = 30.0
    test_timeout = 30.0

    def inference_url(self, connection: ResolvedConnection) -> str:
        return (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{connection.account_id}/ai/run/@cf/cloudflare/{connection.model}"
        )

    def unwrap_response(self, payload: Any) -> dict[str, Any]:
        data = super().unwrap_response(payload)
        if data.get("success") is False:
            raise ValueError(f"{self.descriptor.name} request failed")
        if "result" in data:
            result = data["result"]
            if not isinstance(result, dict):
                raise ValueError(f"{self.descriptor.name} returned an unexpected response format")
            return cast(dict[str, Any], result)
        return data


class LayaProvider(SystemOneProvider):
    """Self-hosted Laya (laya-serve) System One provider."""

    descriptor = PROVIDER_DESCRIPTOR_MAP["laya"]
    timeout = 60.0
    test_timeout = 60.0

    def inference_url(self, connection: ResolvedConnection) -> str:
        return f"{connection.base_url}/v1/systemone"

    def build_request_body(
        self,
        connection: ResolvedConnection,
        state: dict[str, Any],
        questions: dict[str, Any],
    ) -> dict[str, Any]:
        body = super().build_request_body(connection, state, questions)
        # The multilingual checkpoint defaults to 1,024 tokens. Request its 8,192-token
        # window so 6,000-character articles are not silently truncated.
        if connection.model == "multilingual":
            body["max_len"] = 8192
        return body


class CustomSystemOneProvider(SystemOneProvider):
    """Custom System One compatible server provider."""

    descriptor = PROVIDER_DESCRIPTOR_MAP["custom"]
    timeout = 60.0
    test_timeout = 60.0

    def inference_url(self, connection: ResolvedConnection) -> str:
        return f"{connection.base_url}/v1/systemone"


class SystemOneProviderRegistry:
    """Registry mapping System One provider IDs to adapter instances."""

    def __init__(self) -> None:
        self._providers: dict[str, SystemOneProvider] = {}
        self.register(JevProvider())
        self.register(ClefProvider())
        self.register(LayaProvider())
        self.register(CustomSystemOneProvider())

    def register(self, provider: SystemOneProvider) -> None:
        if not isinstance(provider, SystemOneProvider):  # type: ignore[reportUnnecessaryIsInstance]
            raise TypeError(
                f"Provider must be an instance of SystemOneProvider, got {type(provider).__name__}"
            )
        self._providers[provider.descriptor.id] = provider

    def get(self, provider_id: str) -> SystemOneProvider:
        provider = self._providers.get(provider_id)
        if provider is None:
            raise ValueError(f"Unknown model provider: {provider_id}")
        return provider

    def list_providers(self) -> list[SystemOneProvider]:
        return list(self._providers.values())

    def list_descriptors(self) -> list[ProviderDescriptor]:
        return [provider.descriptor for provider in self._providers.values()]


provider_registry = SystemOneProviderRegistry()
set_provider_descriptor_source(lambda: provider_registry.list_descriptors())


def get_provider(provider_id: str) -> SystemOneProvider:
    return provider_registry.get(provider_id)


def list_provider_descriptors() -> list[ProviderDescriptor]:
    return provider_registry.list_descriptors()


def register_provider(provider: SystemOneProvider) -> None:
    provider_registry.register(provider)

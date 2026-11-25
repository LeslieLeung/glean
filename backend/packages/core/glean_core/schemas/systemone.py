"""System One provider configuration, descriptors, and validated results."""

import re
from collections.abc import Sequence
from typing import Annotated, Any, ClassVar, Literal, cast
from urllib.parse import urlsplit, urlunsplit

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

ProviderId = Literal["jev", "clef", "laya", "custom"]
PROVIDER_IDS: tuple[ProviderId, ...] = ("jev", "clef", "laya", "custom")
CLOUDFLARE_ACCOUNT_ID_PATTERN = re.compile(r"^[a-fA-F0-9]{32}$")
_ENDPOINT_SUFFIX_RE = re.compile(r"/v1(?:/(?:systemone|models))?$", re.IGNORECASE)


def _reject_bool_probability(value: Any) -> Any:
    if isinstance(value, bool):
        raise ValueError("Probability must be a number, not a boolean")
    return value


Probability = Annotated[
    float,
    BeforeValidator(_reject_bool_probability),
    Field(ge=0, le=1, allow_inf_nan=False),
]


def normalize_base_url(value: str) -> str:
    """Validate and normalize an HTTP/HTTPS System One base URL."""
    cleaned = value.strip()
    parsed = urlsplit(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Server URL must be an HTTP or HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Server URL must not contain credentials, query parameters or fragments")
    path = parsed.path.rstrip("/")
    path = _ENDPOINT_SUFFIX_RE.sub("", path)
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


class ContentCategory(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    label: str = Field(min_length=1, max_length=40)
    description: str = Field(default="", max_length=2000)


def default_categories() -> list[ContentCategory]:
    return [
        ContentCategory(
            id="original",
            label="Original",
            description="first-hand writing with the author's own reporting, experience, or analysis.",
        ),
        ContentCategory(
            id="repost",
            label="Repost",
            description="copied, aggregated, or lightly rewritten from another source, with little original reporting.",
        ),
        ContentCategory(
            id="ad",
            label="Advertisement",
            description="promotional content. Includes 软广 (reads like an article or review but promotes a brand, product, or service) and 硬广 (explicit sales pitch, price, coupon, or purchase call-to-action).",
        ),
    ]


def _unique_categories(value: list[ContentCategory]) -> list[ContentCategory]:
    if len({item.id for item in value}) != len(value):
        raise ValueError("Category IDs must be unique")
    if len({item.label.casefold() for item in value}) != len(value):
        raise ValueError("Category names must be unique")
    return value


class ProviderDescriptor(BaseModel):
    id: str
    name: str
    default_base_url: str | None = None
    default_model: str | None = None
    suggested_models: list[str] = Field(default_factory=list)
    allow_custom_model: bool = True
    requires_api_key: bool = True
    uses_base_url: bool = True
    uses_account_id: bool = False
    connection_test_runs_inference: bool = False


BUILTIN_PROVIDER_DESCRIPTORS: tuple[ProviderDescriptor, ...] = (
    ProviderDescriptor(
        id="jev",
        name="Jev",
        default_base_url="https://api.typesafe.ai",
        default_model="jev-latest",
        suggested_models=["jev-latest", "jev-preview"],
        allow_custom_model=True,
        requires_api_key=True,
        uses_base_url=True,
        uses_account_id=False,
        connection_test_runs_inference=False,
    ),
    ProviderDescriptor(
        id="clef",
        name="Clef (Cloudflare)",
        default_base_url=None,
        default_model="clef-flash",
        suggested_models=["clef-flash", "clef"],
        allow_custom_model=False,
        requires_api_key=True,
        uses_base_url=False,
        uses_account_id=True,
        connection_test_runs_inference=True,
    ),
    ProviderDescriptor(
        id="laya",
        name="Laya",
        default_base_url="http://localhost:8000",
        default_model="multilingual",
        suggested_models=["multilingual", "english", "typed-decisions"],
        allow_custom_model=True,
        requires_api_key=False,
        uses_base_url=True,
        uses_account_id=False,
        connection_test_runs_inference=True,
    ),
    ProviderDescriptor(
        id="custom",
        name="Custom System One",
        default_base_url=None,
        default_model=None,
        suggested_models=[],
        allow_custom_model=True,
        requires_api_key=False,
        uses_base_url=True,
        uses_account_id=False,
        connection_test_runs_inference=True,
    ),
)

PROVIDER_DESCRIPTOR_MAP: dict[ProviderId, ProviderDescriptor] = {
    cast(ProviderId, descriptor.id): descriptor for descriptor in BUILTIN_PROVIDER_DESCRIPTORS
}


class ProviderProfile(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    base_url: str | None = Field(default=None, max_length=2000)
    model: str | None = Field(default=None, max_length=200)
    account_id: str | None = Field(default=None, max_length=128)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        return normalize_base_url(value)

    @field_validator("model", "account_id")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        return value


class ProviderProfileResponse(ProviderProfile):
    api_key_set: bool = False


def default_provider_profiles() -> dict[ProviderId, ProviderProfile]:
    return {
        pid: ProviderProfile(
            base_url=descriptor.default_base_url,
            model=descriptor.default_model,
            account_id=None,
        )
        for pid, descriptor in PROVIDER_DESCRIPTOR_MAP.items()
    }


class SystemOneSettings(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    enabled: bool = False
    provider: ProviderId = "jev"
    providers: dict[ProviderId, ProviderProfile] = Field(default_factory=default_provider_profiles)
    ai_prompt: str = Field(
        default="Was this text written by an AI language model rather than a human?",
        min_length=1,
        max_length=4000,
    )
    classify_content: bool = True
    content_prompt: str = Field(
        default="Classify this page into exactly one category.",
        min_length=1,
        max_length=4000,
    )
    categories: list[ContentCategory] = Field(
        default_factory=default_categories, min_length=1, max_length=10
    )
    min_text_length: int = Field(default=200, ge=50, le=5000)

    @model_validator(mode="before")
    @classmethod
    def normalize_provider_profiles(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        raw_provider = data.get("provider", "jev")
        merged: Any = {pid: prof.model_dump() for pid, prof in default_provider_profiles().items()}

        raw_providers = data.get("providers")
        if raw_providers is not None:
            if isinstance(raw_providers, dict):
                for pid, prof in cast(dict[Any, Any], raw_providers).items():
                    if pid in merged and isinstance(prof, dict):
                        merged[pid] = {**merged[pid], **cast(dict[str, Any], prof)}
                    elif pid in merged and isinstance(prof, ProviderProfile):
                        merged[pid] = prof.model_dump()
                    else:
                        merged[pid] = prof
            else:
                merged = raw_providers

        for key in ("base_url", "model", "account_id"):
            if key in data:
                field_value = data.pop(key)
                if (
                    isinstance(merged, dict)
                    and isinstance(raw_provider, str)
                    and raw_provider in merged
                    and isinstance(merged[raw_provider], dict)
                ):
                    merged[raw_provider][key] = field_value

        data["providers"] = merged
        return data

    @field_validator("categories")
    @classmethod
    def unique_categories(cls, value: list[ContentCategory]) -> list[ContentCategory]:
        return _unique_categories(value)

    @property
    def active_profile(self) -> ProviderProfile:
        return self.providers[self.provider]

    @property
    def base_url(self) -> str | None:
        return self.active_profile.base_url

    @property
    def model(self) -> str | None:
        return self.active_profile.model

    @property
    def account_id(self) -> str | None:
        return self.active_profile.account_id


def _empty_provider_api_keys() -> dict[ProviderId, str]:
    return {}


class SystemOneConfig(SystemOneSettings):
    NAMESPACE: ClassVar[str] = "jev"
    provider_api_keys: dict[ProviderId, str] = Field(
        default_factory=_empty_provider_api_keys, repr=False
    )
    version: str = "initial"

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_config(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        # Older installations stored this preference in the system config.
        data.pop("show_confidence", None)

        raw_keys = data.get("provider_api_keys")
        cleaned_keys: dict[Any, Any] | None = None
        if raw_keys is None:
            cleaned_keys = {}
        elif isinstance(raw_keys, dict):
            cleaned_keys = {}
            for pid, key in cast(dict[Any, Any], raw_keys).items():
                if isinstance(key, str):
                    stripped = key.strip()
                    if stripped:
                        cleaned_keys[pid] = stripped
                else:
                    cleaned_keys[pid] = key

        if "api_key" in data:
            legacy_key = data.pop("api_key")
            raw_provider = data.get("provider", "jev")
            if (
                cleaned_keys is not None
                and isinstance(raw_provider, str)
                and raw_provider in PROVIDER_DESCRIPTOR_MAP
            ):
                if isinstance(legacy_key, str):
                    stripped_key = legacy_key.strip()
                    if stripped_key:
                        cleaned_keys[raw_provider] = stripped_key
                    else:
                        cleaned_keys.pop(raw_provider, None)
                elif legacy_key is None:
                    cleaned_keys.pop(raw_provider, None)
                else:
                    cleaned_keys[raw_provider] = legacy_key

        data["provider_api_keys"] = cleaned_keys if cleaned_keys is not None else raw_keys
        return data

    @field_validator("provider_api_keys")
    @classmethod
    def validate_provider_api_keys(cls, value: dict[ProviderId, str]) -> dict[ProviderId, str]:
        cleaned: dict[ProviderId, str] = {}
        for pid, key in value.items():
            stripped = key.strip()
            if len(stripped) > 4000:
                raise ValueError("API key must be at most 4000 characters")
            if stripped:
                cleaned[pid] = stripped
        return cleaned

    @property
    def api_key(self) -> str | None:
        return self.provider_api_keys.get(self.provider)


class SystemOneConfigRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    enabled: bool = False
    provider: ProviderId | None = None
    providers: dict[ProviderId, ProviderProfile] | None = None
    base_url: str | None = Field(default=None, max_length=2000)
    model: str | None = Field(default=None, max_length=200)
    account_id: str | None = Field(default=None, max_length=128)
    # Omitted/null preserves the saved key; an empty string clears it.
    api_key: str | None = Field(default=None, repr=False, max_length=4000)
    provider_api_keys: dict[ProviderId, str | None] | None = Field(default=None, repr=False)
    ai_prompt: str = Field(
        default="Was this text written by an AI language model rather than a human?",
        min_length=1,
        max_length=4000,
    )
    classify_content: bool = True
    content_prompt: str = Field(
        default="Classify this page into exactly one category.",
        min_length=1,
        max_length=4000,
    )
    categories: list[ContentCategory] = Field(
        default_factory=default_categories, min_length=1, max_length=10
    )
    min_text_length: int = Field(default=200, ge=50, le=5000)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        return normalize_base_url(value)

    @field_validator("model", "account_id")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        return value

    @field_validator("provider_api_keys")
    @classmethod
    def validate_provider_api_keys(
        cls, value: dict[ProviderId, str | None] | None
    ) -> dict[ProviderId, str | None] | None:
        if value is None:
            return None
        cleaned: dict[ProviderId, str | None] = {}
        for pid, key in value.items():
            if key is None:
                cleaned[pid] = None
            else:
                stripped = key.strip()
                if len(stripped) > 4000:
                    raise ValueError("API key must be at most 4000 characters")
                cleaned[pid] = stripped
        return cleaned

    @field_validator("categories")
    @classmethod
    def unique_categories(cls, value: list[ContentCategory]) -> list[ContentCategory]:
        return _unique_categories(value)


class SystemOneConfigResponse(BaseModel):
    enabled: bool
    provider: ProviderId
    base_url: str | None
    model: str | None
    account_id: str | None
    api_key_set: bool
    providers: dict[ProviderId, ProviderProfileResponse]
    available_providers: list[ProviderDescriptor]
    ai_prompt: str
    classify_content: bool
    content_prompt: str
    categories: list[ContentCategory]
    min_text_length: int
    defaults: SystemOneSettings = Field(default_factory=SystemOneSettings)

    @classmethod
    def from_config(
        cls,
        config: SystemOneConfig,
        descriptors: Sequence[ProviderDescriptor] | None = None,
    ) -> "SystemOneConfigResponse":
        active = config.active_profile
        providers: dict[ProviderId, ProviderProfileResponse] = {
            pid: ProviderProfileResponse(
                **config.providers.get(pid, ProviderProfile()).model_dump(),
                api_key_set=bool(config.provider_api_keys.get(pid)),
            )
            for pid in PROVIDER_IDS
        }
        available = (
            list(descriptors) if descriptors is not None else list(BUILTIN_PROVIDER_DESCRIPTORS)
        )
        return cls(
            enabled=config.enabled,
            provider=config.provider,
            base_url=active.base_url,
            model=active.model,
            account_id=active.account_id,
            api_key_set=bool(config.api_key),
            providers=providers,
            available_providers=available,
            ai_prompt=config.ai_prompt,
            classify_content=config.classify_content,
            content_prompt=config.content_prompt,
            categories=config.categories,
            min_text_length=config.min_text_length,
        )


class ContentClassification(BaseModel):
    label: str
    name: str
    confidence: Probability


class EntryClassification(BaseModel):
    label: Literal["human", "ai"]
    score: Probability
    model_id: str
    provider: str | None = None
    content: ContentClassification | None = None


class SystemOneNoulAnswer(BaseModel):
    noul: Probability


class SystemOneChoiceAnswer(BaseModel):
    choice: str
    confidence: Probability | None = None
    probabilities: dict[str, Probability] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_confidence(self) -> "SystemOneChoiceAnswer":
        if self.confidence is None:
            self.confidence = self.probabilities.get(self.choice)
        if self.confidence is None:
            raise ValueError("Model did not return category confidence")
        return self


class SystemOneAnswers(BaseModel):
    ai_generated: SystemOneNoulAnswer
    content_type: SystemOneChoiceAnswer | None = None


class SystemOneResponse(BaseModel):
    model: str | None = None
    answers: SystemOneAnswers

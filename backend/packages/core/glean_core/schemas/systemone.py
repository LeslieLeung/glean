"""System One provider configuration, descriptors, and validated results."""

import re
from collections.abc import Callable, Sequence
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

ProviderId = str
PROVIDER_IDS: tuple[str, ...] = ("jev", "clef", "laya", "custom")
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

# Stable id of the built-in advertisement category. Ranking keys off this id.
AD_CATEGORY_ID = "ad"


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
            description="First-hand writing featuring the author's own analysis, experience, tutorial, independent review, or opinion.",
        ),
        ContentCategory(
            id="news",
            label="News",
            description="Timely reporting or briefs covering events, industry updates, or announcements written by media or observers, rather than deep first-hand analysis.",
        ),
        ContentCategory(
            id="release",
            label="Release",
            description="Official release notes, changelogs, security advisories, or factual product or project updates focused on what changed, rather than commercial sales promotion.",
        ),
        ContentCategory(
            id="digest",
            label="Digest",
            description="Curated roundups, weekly newsletters, or link collections that summarize or select multiple external items with editorial curation.",
        ),
        ContentCategory(
            id="translation",
            label="Translation",
            description="Faithful translation or localized edition of an article originally published in another language, preserving the source work rather than low-effort scraping or light rewriting.",
        ),
        ContentCategory(
            id="repost",
            label="Repost",
            description="Copied, scraped, syndicated, or lightly rewritten content from another source with little original reporting, analysis, translation, or curation.",
        ),
        ContentCategory(
            id=AD_CATEGORY_ID,
            label="Advertisement",
            description="Promotional or sponsored content aimed at selling a product, brand, or service—including 软广 (advertorials disguised as articles or reviews) and 硬广 (explicit sales pitches, discounts, coupons, or purchase CTAs). Excludes factual release notes and independent reviews.",
        ),
    ]


def _unique_categories(value: list[ContentCategory]) -> list[ContentCategory]:
    if len({item.id for item in value}) != len(value):
        raise ValueError("Category IDs must be unique")
    if len({item.label.casefold() for item in value}) != len(value):
        raise ValueError("Category names must be unique")
    return value


class ProviderDescriptor(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
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

PROVIDER_DESCRIPTOR_MAP: dict[str, ProviderDescriptor] = {
    descriptor.id: descriptor for descriptor in BUILTIN_PROVIDER_DESCRIPTORS
}

_provider_descriptor_source: Callable[[], Sequence[ProviderDescriptor]] | None = None


def set_provider_descriptor_source(
    source: Callable[[], Sequence[ProviderDescriptor]] | None,
) -> None:
    """Bind the live provider descriptor source used by schema validation and defaults."""
    global _provider_descriptor_source
    _provider_descriptor_source = source


def registered_provider_descriptors() -> dict[str, ProviderDescriptor]:
    descriptors = (
        _provider_descriptor_source()
        if _provider_descriptor_source is not None
        else BUILTIN_PROVIDER_DESCRIPTORS
    )
    return {descriptor.id: descriptor for descriptor in descriptors}


def validate_registered_provider_id(value: str) -> str:
    descriptors = registered_provider_descriptors()
    if value not in descriptors:
        allowed = ", ".join(descriptors)
        raise ValueError(f"Unknown model provider '{value}'. Expected one of: {allowed}")
    return value


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


def default_provider_profiles(
    descriptors: Sequence[ProviderDescriptor] | None = None,
) -> dict[ProviderId, ProviderProfile]:
    descriptor_map = (
        {descriptor.id: descriptor for descriptor in descriptors}
        if descriptors is not None
        else registered_provider_descriptors()
    )
    return {
        pid: ProviderProfile(
            base_url=descriptor.default_base_url,
            model=descriptor.default_model,
            account_id=None,
        )
        for pid, descriptor in descriptor_map.items()
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
        default=(
            "Classify this RSS article into exactly one category based on its primary purpose. "
            "Treat factual changelogs and release notes as release rather than ad, "
            "curated link roundups as digest rather than repost, "
            "and faithful cross-language translations as translation rather than repost."
        ),
        min_length=1,
        max_length=4000,
    )
    categories: list[ContentCategory] = Field(
        default_factory=default_categories, min_length=1, max_length=10
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_provider_profiles(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(cast(dict[str, Any], value))
        raw_provider = data.get("provider", "jev")
        normalized_provider = (
            raw_provider.strip() if isinstance(raw_provider, str) else raw_provider
        )
        merged: Any = {pid: prof.model_dump() for pid, prof in default_provider_profiles().items()}

        raw_providers = data.get("providers")
        if raw_providers is not None:
            if isinstance(raw_providers, dict):
                for pid, prof in cast(dict[Any, Any], raw_providers).items():
                    norm_pid = pid.strip() if isinstance(pid, str) else pid
                    if norm_pid in merged and isinstance(prof, dict):
                        merged[norm_pid] = {**merged[norm_pid], **cast(dict[str, Any], prof)}
                    elif norm_pid in merged and isinstance(prof, ProviderProfile):
                        merged[norm_pid] = prof.model_dump()
                    else:
                        merged[pid] = prof
            else:
                merged = raw_providers

        for key in ("base_url", "model", "account_id"):
            if key in data:
                field_value = data.pop(key)
                if (
                    isinstance(merged, dict)
                    and isinstance(normalized_provider, str)
                    and normalized_provider in merged
                    and isinstance(merged[normalized_provider], dict)
                ):
                    merged[normalized_provider][key] = field_value

        data["providers"] = merged
        return data

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        return validate_registered_provider_id(value)

    @field_validator("providers")
    @classmethod
    def validate_providers(
        cls, value: dict[ProviderId, ProviderProfile]
    ) -> dict[ProviderId, ProviderProfile]:
        for pid in value:
            validate_registered_provider_id(pid)
        return value

    @field_validator("categories")
    @classmethod
    def unique_categories(cls, value: list[ContentCategory]) -> list[ContentCategory]:
        return _unique_categories(value)

    @property
    def active_profile(self) -> ProviderProfile:
        if self.provider in self.providers:
            return self.providers[self.provider]
        descriptor = registered_provider_descriptors().get(self.provider)
        if descriptor is not None:
            return ProviderProfile(
                base_url=descriptor.default_base_url,
                model=descriptor.default_model,
                account_id=None,
            )
        return ProviderProfile()

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
        # Older installations stored these settings in the system config.
        data.pop("show_confidence", None)
        data.pop("min_text_length", None)

        raw_keys = data.get("provider_api_keys")
        cleaned_keys: dict[Any, Any] | None = None
        if raw_keys is None:
            cleaned_keys = {}
        elif isinstance(raw_keys, dict):
            cleaned_keys = {}
            for pid, key in cast(dict[Any, Any], raw_keys).items():
                if isinstance(key, str):
                    cleaned_keys[pid] = key.strip()
                else:
                    cleaned_keys[pid] = key

        if "api_key" in data:
            legacy_key = data.pop("api_key")
            raw_provider = data.get("provider", "jev")
            normalized_provider = (
                raw_provider.strip() if isinstance(raw_provider, str) else raw_provider
            )
            if (
                cleaned_keys is not None
                and isinstance(normalized_provider, str)
                and normalized_provider in registered_provider_descriptors()
            ):
                if isinstance(legacy_key, str):
                    stripped_key = legacy_key.strip()
                    if stripped_key:
                        cleaned_keys[normalized_provider] = stripped_key
                    else:
                        cleaned_keys.pop(normalized_provider, None)
                elif legacy_key is None:
                    cleaned_keys.pop(normalized_provider, None)
                else:
                    cleaned_keys[normalized_provider] = legacy_key

        data["provider_api_keys"] = cleaned_keys if cleaned_keys is not None else raw_keys
        return data

    @field_validator("provider_api_keys")
    @classmethod
    def validate_provider_api_keys(cls, value: dict[ProviderId, str]) -> dict[ProviderId, str]:
        cleaned: dict[ProviderId, str] = {}
        for pid, key in value.items():
            validate_registered_provider_id(pid)
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
        default=(
            "Classify this RSS article into exactly one category based on its primary purpose. "
            "Treat factual changelogs and release notes as release rather than ad, "
            "curated link roundups as digest rather than repost, "
            "and faithful cross-language translations as translation rather than repost."
        ),
        min_length=1,
        max_length=4000,
    )
    categories: list[ContentCategory] = Field(
        default_factory=default_categories, min_length=1, max_length=10
    )

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_registered_provider_id(value)

    @field_validator("providers")
    @classmethod
    def validate_providers(
        cls, value: dict[ProviderId, ProviderProfile] | None
    ) -> dict[ProviderId, ProviderProfile] | None:
        if value is None:
            return None
        for pid in value:
            validate_registered_provider_id(pid)
        return value

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
            validate_registered_provider_id(pid)
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
    defaults: SystemOneSettings = Field(default_factory=SystemOneSettings)

    @classmethod
    def from_config(
        cls,
        config: SystemOneConfig,
        descriptors: Sequence[ProviderDescriptor] | None = None,
    ) -> "SystemOneConfigResponse":
        active = config.active_profile
        available = (
            list(descriptors)
            if descriptors is not None
            else list(registered_provider_descriptors().values())
        )
        default_profiles = default_provider_profiles(available)
        provider_ids = list(
            dict.fromkeys([*(item.id for item in available), *config.providers.keys()])
        )
        providers: dict[ProviderId, ProviderProfileResponse] = {
            pid: ProviderProfileResponse(
                **config.providers.get(
                    pid, default_profiles.get(pid, ProviderProfile())
                ).model_dump(),
                api_key_set=bool(config.provider_api_keys.get(pid)),
            )
            for pid in provider_ids
        }
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

"""Jev detection configuration and validated results."""

from typing import Annotated, ClassVar, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


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


class JevSettings(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    enabled: bool = False
    base_url: str = "https://api.typesafe.ai"
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
    show_confidence: bool = False

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Jev server must be an HTTP or HTTPS URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError(
                "Jev server must not contain credentials, query parameters or fragments"
            )
        # Also accept a pasted API endpoint, as Aletheia does.
        value = value.rstrip("/")
        for suffix in ("/v1/systemone", "/v1/models"):
            if value.endswith(suffix):
                value = value[: -len(suffix)]
        return value

    @field_validator("categories")
    @classmethod
    def unique_categories(cls, value: list[ContentCategory]) -> list[ContentCategory]:
        if len({item.id for item in value}) != len(value):
            raise ValueError("Category IDs must be unique")
        if len({item.label.casefold() for item in value}) != len(value):
            raise ValueError("Category names must be unique")
        return value


class JevConfig(JevSettings):
    NAMESPACE: ClassVar[str] = "jev"
    api_key: str | None = Field(default=None, repr=False)
    version: str = "initial"


class JevConfigRequest(JevSettings):
    # Omitted/null preserves the saved key; an empty string clears it.
    api_key: str | None = Field(default=None, repr=False, max_length=4000)


class JevConfigResponse(JevSettings):
    api_key_set: bool
    defaults: JevSettings = Field(default_factory=JevSettings)

    @classmethod
    def from_config(cls, config: JevConfig) -> "JevConfigResponse":
        return cls(
            **config.model_dump(exclude={"api_key", "version"}), api_key_set=bool(config.api_key)
        )


class ContentClassification(BaseModel):
    label: str
    name: str
    confidence: Probability


class EntryClassification(BaseModel):
    label: Literal["human", "ai"]
    score: Probability
    model_id: str
    content: ContentClassification | None = None
    show_confidence: bool = False


class JevNoulAnswer(BaseModel):
    noul: Probability


class JevChoiceAnswer(BaseModel):
    choice: str
    confidence: Probability | None = None
    probabilities: dict[str, Probability] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_confidence(self) -> "JevChoiceAnswer":
        if self.confidence is None:
            self.confidence = self.probabilities.get(self.choice)
        if self.confidence is None:
            raise ValueError("Jev did not return category confidence")
        return self


class JevAnswers(BaseModel):
    ai_generated: JevNoulAnswer
    content_type: JevChoiceAnswer | None = None


class JevResponse(BaseModel):
    model: str = "jev-latest"
    answers: JevAnswers

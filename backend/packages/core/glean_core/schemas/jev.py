"""Backward-compatible Jev schema aliases for System One."""

from .systemone import (
    ContentCategory,
    ContentClassification,
    EntryClassification,
    Probability,
    SystemOneAnswers,
    SystemOneChoiceAnswer,
    SystemOneConfig,
    SystemOneConfigRequest,
    SystemOneConfigResponse,
    SystemOneNoulAnswer,
    SystemOneResponse,
    SystemOneSettings,
    default_categories,
)

JevSettings = SystemOneSettings
JevConfig = SystemOneConfig
JevConfigRequest = SystemOneConfigRequest
JevConfigResponse = SystemOneConfigResponse
JevNoulAnswer = SystemOneNoulAnswer
JevChoiceAnswer = SystemOneChoiceAnswer
JevAnswers = SystemOneAnswers
JevResponse = SystemOneResponse

__all__ = [
    "ContentCategory",
    "ContentClassification",
    "EntryClassification",
    "JevAnswers",
    "JevChoiceAnswer",
    "JevConfig",
    "JevConfigRequest",
    "JevConfigResponse",
    "JevNoulAnswer",
    "JevResponse",
    "JevSettings",
    "Probability",
    "default_categories",
]

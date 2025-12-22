"""Preference-related schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class SourceAffinity(BaseModel):
    """Source affinity data."""

    source_name: str
    affinity_score: float


class AuthorAffinity(BaseModel):
    """Author affinity data."""

    author_name: str
    affinity_score: float


class UserPreferenceVector(BaseModel):
    """User preference vector representation."""

    user_id: str
    vector_type: str = Field(..., description="positive or negative")
    embedding: list[float]
    sample_count: float
    updated_at: datetime


class ScoreFactors(BaseModel):
    """Score calculation factors for debugging."""

    positive_sim: float = Field(..., description="Similarity to positive preferences")
    negative_sim: float = Field(..., description="Similarity to negative preferences")
    confidence: float = Field(..., description="Model confidence based on sample count")
    source_boost: float = Field(default=0.0, description="Boost from source affinity")
    author_boost: float = Field(default=0.0, description="Boost from author affinity")


class PreferenceStats(BaseModel):
    """User preference statistics."""

    user_id: str
    total_likes: int
    total_dislikes: int
    total_bookmarks: int
    preference_strength: str = Field(..., description="weak, moderate, or strong")
    top_sources: list[SourceAffinity] = Field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    top_authors: list[AuthorAffinity] = Field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    model_updated_at: datetime | None = None

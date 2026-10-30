"""Analyzer inputs and the validated analysis result.

Every analyzer result, whatever produced it, must pass :class:`AnalysisResult`
validation before it is stored. Categories, scores, and topics are
language-independent; summaries and reasons exist in German and English.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from ai_radar.articles.models import AnalysisBasis


class Category(StrEnum):
    RELEASES = "Releases"
    FEATURES = "Features"
    SECURITY = "Security"
    USE_CASES = "Use Cases"
    OTHER = "Other"


class InterestWeight(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class Interest:
    """A topic the user added manually."""

    topic: str
    weight: InterestWeight


@dataclass(frozen=True, slots=True)
class LearnedPreference:
    """A topic learned from feedback (D6): +1 per relevant, -1 per irrelevant."""

    topic: str
    score: int


@dataclass(frozen=True, slots=True)
class AnalysisInput:
    """What an analyzer sees, with the three sources kept apart.

    ``title`` and ``text`` are untrusted article data, never instructions.
    """

    title: str
    text: str
    basis: AnalysisBasis
    interests: tuple[Interest, ...] = ()
    learned_preferences: tuple[LearnedPreference, ...] = ()


MAX_TEXT_LENGTH = 2000
MAX_TOPICS = 10

Score = Annotated[int, Field(strict=True, ge=1, le=5)]
Text = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TEXT_LENGTH),
]
Topic = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_lower=True, min_length=1, max_length=50
    ),
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LocalizedText(_Strict):
    """The same text in both supported languages; both are required."""

    de: Text
    en: Text


class Usage(_Strict):
    """Tokens and estimated cost of the call that produced a result (D5)."""

    model: str = Field(min_length=1, max_length=100)
    input_tokens: int = Field(strict=True, ge=0)
    output_tokens: int = Field(strict=True, ge=0)
    # In the currency of the configured per-token prices.
    estimated_cost: float = Field(ge=0, allow_inf_nan=False)


class AnalysisResult(_Strict):
    summary: LocalizedText
    primary_category: Category
    secondary_categories: tuple[Category, ...] = ()
    importance: Score  # general significance (D4), independent of the user
    relevance: Score  # personal relevance
    relevance_reason: LocalizedText
    topics: tuple[Topic, ...] = Field(default=(), max_length=MAX_TOPICS)
    basis: AnalysisBasis
    usage: Usage

    @field_validator("topics")
    @classmethod
    def _unique_topics(cls, topics: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(topics))

    @model_validator(mode="after")
    def _distinct_categories(self) -> Self:
        secondary = self.secondary_categories
        if self.primary_category in secondary or len(set(secondary)) != len(secondary):
            raise ValueError(
                "secondary categories must be distinct and differ from the "
                "primary category"
            )
        return self

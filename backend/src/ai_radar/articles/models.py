"""Article data model, independent of storage and API."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ArticleStatus(StrEnum):
    NEW = "new"
    PROCESSING = "processing"
    ANALYZED = "analyzed"
    FAILED = "failed"


class AnalysisBasis(StrEnum):
    """Which text an analysis uses: the extracted page or the feed excerpt."""

    FULL_TEXT = "full_text"
    EXCERPT = "excerpt"


@dataclass(frozen=True, slots=True)
class NewArticle:
    """An article as collected, before it has been stored."""

    source: str
    url: str
    title: str
    content: str | None
    published_at: datetime | None
    collected_at: datetime
    feed_id: int | None = None  # None for articles not collected from a stored feed

    def __post_init__(self) -> None:
        for name in ("published_at", "collected_at"):
            value = getattr(self, name)
            # A tzinfo whose utcoffset() is None still counts as naive.
            if value is not None and value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class Article:
    """A stored article."""

    id: int
    source: str
    url: str
    normalized_url: str
    title: str
    content: str | None
    published_at: datetime | None
    collected_at: datetime
    status: ArticleStatus
    feed_id: int | None
    full_text: str | None = None
    analysis_basis: AnalysisBasis | None = None  # None: collected before D3
    analysis_attempts: int = 0  # finished analysis attempts
    analysis_error: str | None = None  # safe message of the last failure
    analysis_attempted_at: datetime | None = None

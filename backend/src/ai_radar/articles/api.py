"""HTTP API for reading articles: ``GET /api/articles``.

Responses are JSON data. Titles, excerpts, summaries, and reasons come from
untrusted feeds and model output; clients must render them as text (D8).
"""

from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import AfterValidator, BaseModel

from ai_radar.analysis.models import Category
from ai_radar.articles.listing import (
    MAX_PAGE_SIZE,
    MAX_SEARCH_LENGTH,
    ArticleQuery,
    Language,
    ListedArticle,
    SortOrder,
    list_articles,
)
from ai_radar.articles.models import AnalysisBasis, ArticleStatus
from ai_radar.db import connect
from ai_radar.feedback.repository import Rating

# Polling clients pass next_since back as since. It lies a little before the
# request so changes committed while the request ran are not missed; items
# may therefore be delivered twice.
POLL_OVERLAP = timedelta(seconds=5)
MAX_OFFSET = 1_000_000

router = APIRouter(prefix="/api/articles", tags=["articles"])


def _require_timezone(value: datetime | None) -> datetime | None:
    if value is not None and value.utcoffset() is None:
        raise ValueError("must include a timezone, e.g. 2026-10-30T12:00:00Z")
    return value


AwareDatetime = Annotated[datetime | None, AfterValidator(_require_timezone)]


class AnalysisOut(BaseModel):
    primary_category: Category
    secondary_categories: list[Category]
    importance: int
    relevance: int
    topics: list[str]
    basis: AnalysisBasis
    summary: str
    relevance_reason: str
    analyzed_at: datetime


class ArticleOut(BaseModel):
    id: int
    source: str
    url: str
    title: str
    excerpt: str | None
    published_at: datetime | None
    collected_at: datetime
    status: ArticleStatus
    analysis_error: str | None
    has_full_text: bool
    analysis: AnalysisOut | None
    feedback: Rating | None
    changed_at: datetime

    @classmethod
    def from_item(cls, item: ListedArticle) -> "ArticleOut":
        analysis = None
        if item.analysis is not None:
            a = item.analysis
            analysis = AnalysisOut(
                primary_category=a.primary_category,
                secondary_categories=list(a.secondary_categories),
                importance=a.importance,
                relevance=a.relevance,
                topics=list(a.topics),
                basis=a.basis,
                summary=a.summary,
                relevance_reason=a.relevance_reason,
                analyzed_at=a.analyzed_at,
            )
        return cls(
            id=item.id,
            source=item.source,
            url=item.url,
            title=item.title,
            excerpt=item.excerpt,
            published_at=item.published_at,
            collected_at=item.collected_at,
            status=item.status,
            analysis_error=item.analysis_error,
            has_full_text=item.has_full_text,
            analysis=analysis,
            feedback=item.feedback,
            changed_at=item.changed_at,
        )


class ArticleListOut(BaseModel):
    items: list[ArticleOut]
    total: int
    limit: int
    offset: int
    next_since: datetime


@router.get("")
def get_articles(
    request: Request,
    lang: Language = "de",
    q: Annotated[str | None, Query(max_length=MAX_SEARCH_LENGTH)] = None,
    category: Category | None = None,
    min_relevance: Annotated[int | None, Query(ge=1, le=5)] = None,
    published_from: AwareDatetime = None,
    published_to: AwareDatetime = None,
    since: AwareDatetime = None,
    sort: SortOrder = SortOrder.RECENT,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> ArticleListOut:
    if published_from and published_to and published_from > published_to:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "published_from must not be after published_to",
        )
    started = datetime.now(UTC)
    query = ArticleQuery(
        lang=lang,
        search=q,
        category=category,
        min_relevance=min_relevance,
        published_from=published_from,
        published_to=published_to,
        since=since,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    db_path: Path = request.app.state.db_path
    with closing(connect(db_path)) as conn:
        try:
            page = list_articles(conn, query)
        except ValueError as exc:  # e.g. too many search terms
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)
            ) from None
    return ArticleListOut(
        items=[ArticleOut.from_item(item) for item in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
        next_since=started - POLL_OVERLAP,
    )

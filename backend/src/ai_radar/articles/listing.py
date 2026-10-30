"""Read model for listing articles with their latest analysis (FR-21, FR-22).

The whole listing is one constant SQL query: filters, sort order, language,
and paging are bound parameters, so no SQL is built from user input.

Articles are never filtered out by their status (FR-34): unanalyzed and failed
articles are listed with their status, but have no analysis and therefore do
not match category or relevance filters.

``changed_at`` is the latest of collection, analysis, analysis attempt, and
feedback; ``since`` returns only articles changed after it, for polling.
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from ai_radar.analysis.models import Category
from ai_radar.articles.models import AnalysisBasis, ArticleStatus
from ai_radar.feedback.repository import Rating

Language = Literal["de", "en"]
MAX_PAGE_SIZE = 100


class SortOrder(StrEnum):
    RECENT = "recent"  # publication date, else collection date; newest first
    RELEVANCE = "relevance"  # personal relevance, then recent; unanalyzed last


@dataclass(frozen=True, slots=True)
class ArticleQuery:
    lang: Language = "de"
    category: Category | None = None
    min_relevance: int | None = None
    published_from: datetime | None = None
    published_to: datetime | None = None
    since: datetime | None = None
    sort: SortOrder = SortOrder.RECENT
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class ListedAnalysis:
    primary_category: Category
    secondary_categories: tuple[Category, ...]
    importance: int
    relevance: int
    topics: tuple[str, ...]
    basis: AnalysisBasis
    summary: str  # in the requested language
    relevance_reason: str  # in the requested language
    analyzed_at: datetime


@dataclass(frozen=True, slots=True)
class ListedArticle:
    id: int
    source: str
    url: str
    title: str
    excerpt: str | None  # untrusted feed text, may contain HTML
    published_at: datetime | None
    collected_at: datetime
    status: ArticleStatus
    analysis_error: str | None
    has_full_text: bool
    analysis: ListedAnalysis | None
    feedback: Rating | None
    changed_at: datetime


@dataclass(frozen=True, slots=True)
class ArticlePage:
    items: list[ListedArticle]
    total: int


_LIST_ARTICLES = """
WITH latest AS (
    SELECT article_id, MAX(id) AS id FROM analyses GROUP BY article_id
),
items AS (
    SELECT a.id, a.source, a.url, a.title, a.content, a.published_at,
           a.collected_at, a.status, a.analysis_error,
           a.full_text IS NOT NULL AS has_full_text,
           an.primary_category, an.secondary_categories, an.importance,
           an.relevance, an.topics, an.analysis_basis, an.analyzed_at,
           t.summary, t.relevance_reason, f.rating,
           COALESCE(a.published_at, a.collected_at) AS sort_date,
           MAX(a.collected_at,
               COALESCE(an.analyzed_at, ''),
               COALESCE(a.analysis_attempted_at, ''),
               COALESCE(f.updated_at, '')) AS changed_at
    FROM articles AS a
    LEFT JOIN latest ON latest.article_id = a.id
    LEFT JOIN analyses AS an ON an.id = latest.id
    LEFT JOIN analysis_texts AS t
           ON t.analysis_id = an.id AND t.language = :lang
    LEFT JOIN article_feedback AS f ON f.article_id = a.id
)
SELECT items.*, COUNT(*) OVER () AS total
FROM items
WHERE (:category IS NULL
       OR primary_category = :category
       OR EXISTS (SELECT 1 FROM json_each(items.secondary_categories)
                  WHERE value = :category))
  AND (:min_relevance IS NULL OR relevance >= :min_relevance)
  AND (:published_from IS NULL OR sort_date >= :published_from)
  AND (:published_to IS NULL OR sort_date <= :published_to)
  AND (:since IS NULL OR changed_at > :since)
ORDER BY CASE WHEN :sort = 'relevance' THEN relevance IS NULL ELSE 0 END,
         CASE WHEN :sort = 'relevance' THEN relevance END DESC,
         sort_date DESC,
         id DESC
LIMIT :limit OFFSET :offset
"""


def _to_db(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(UTC).isoformat()


def _to_datetime(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _row_to_item(row: sqlite3.Row) -> ListedArticle:
    analysis = None
    if row["primary_category"] is not None:
        analysis = ListedAnalysis(
            primary_category=Category(row["primary_category"]),
            secondary_categories=tuple(
                Category(c) for c in json.loads(row["secondary_categories"])
            ),
            importance=row["importance"],
            relevance=row["relevance"],
            topics=tuple(json.loads(row["topics"])),
            basis=AnalysisBasis(row["analysis_basis"]),
            summary=row["summary"],
            relevance_reason=row["relevance_reason"],
            analyzed_at=datetime.fromisoformat(row["analyzed_at"]),
        )
    collected_at = datetime.fromisoformat(row["collected_at"])
    return ListedArticle(
        id=row["id"],
        source=row["source"],
        url=row["url"],
        title=row["title"],
        excerpt=row["content"],
        published_at=_to_datetime(row["published_at"]),
        collected_at=collected_at,
        status=ArticleStatus(row["status"]),
        analysis_error=row["analysis_error"],
        has_full_text=bool(row["has_full_text"]),
        analysis=analysis,
        feedback=None if row["rating"] is None else Rating(row["rating"]),
        changed_at=datetime.fromisoformat(row["changed_at"]),
    )


def list_articles(conn: sqlite3.Connection, query: ArticleQuery) -> ArticlePage:
    if not 1 <= query.limit <= MAX_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
    params = {
        "lang": query.lang,
        "category": None if query.category is None else str(query.category),
        "min_relevance": query.min_relevance,
        "published_from": _to_db(query.published_from),
        "published_to": _to_db(query.published_to),
        "since": _to_db(query.since),
        "sort": str(query.sort),
        "limit": query.limit,
        "offset": query.offset,
    }
    rows = conn.execute(_LIST_ARTICLES, params).fetchall()
    if rows:
        total = rows[0]["total"]
    elif query.offset:
        # Past the last page: count with the same query from the start.
        first = conn.execute(
            _LIST_ARTICLES, {**params, "limit": 1, "offset": 0}
        ).fetchall()
        total = first[0]["total"] if first else 0
    else:
        total = 0
    return ArticlePage(items=[_row_to_item(row) for row in rows], total=total)

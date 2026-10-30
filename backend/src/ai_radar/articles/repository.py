"""Database access for articles."""

import sqlite3
from datetime import UTC, datetime

from ai_radar.articles.models import Article, ArticleStatus, NewArticle
from ai_radar.articles.url import normalize_url
from ai_radar.db import fetch_one, transaction


def _to_db(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(UTC).isoformat()


def _from_db(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _row_to_article(row: sqlite3.Row) -> Article:
    collected_at = _from_db(row["collected_at"])
    assert collected_at is not None  # NOT NULL in the schema
    return Article(
        id=row["id"],
        source=row["source"],
        url=row["url"],
        normalized_url=row["normalized_url"],
        title=row["title"],
        content=row["content"],
        published_at=_from_db(row["published_at"]),
        collected_at=collected_at,
        status=ArticleStatus(row["status"]),
    )


class ArticleRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, article: NewArticle) -> Article | None:
        """Store a new article; return ``None`` if its URL is already stored.

        Existing articles are never overwritten.
        """
        normalized_url = normalize_url(article.url)
        with transaction(self._conn):
            row = fetch_one(
                self._conn,
                """
                INSERT INTO articles
                    (source, url, normalized_url, title, content,
                     published_at, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (normalized_url) DO NOTHING
                RETURNING *
                """,
                (
                    article.source,
                    article.url,
                    normalized_url,
                    article.title,
                    article.content,
                    _to_db(article.published_at),
                    _to_db(article.collected_at),
                ),
            )
        return None if row is None else _row_to_article(row)

    def get_by_id(self, article_id: int) -> Article | None:
        row = fetch_one(
            self._conn, "SELECT * FROM articles WHERE id = ?", (article_id,)
        )
        return None if row is None else _row_to_article(row)

    def get_by_url(self, url: str) -> Article | None:
        """Look up an article by any URL that normalizes to the stored one.

        Raises ``ValueError`` if ``url`` is not an acceptable article URL.
        """
        row = fetch_one(
            self._conn,
            "SELECT * FROM articles WHERE normalized_url = ?",
            (normalize_url(url),),
        )
        return None if row is None else _row_to_article(row)

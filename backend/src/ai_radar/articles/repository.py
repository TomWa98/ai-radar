"""Database access for articles."""

import sqlite3
from datetime import UTC, datetime

from ai_radar.articles.models import (
    AnalysisBasis,
    Article,
    ArticleStatus,
    NewArticle,
)
from ai_radar.articles.url import normalize_url
from ai_radar.db import fetch_one, transaction

MAX_ANALYSIS_ERROR_LENGTH = 500


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
        feed_id=row["feed_id"],
        full_text=row["full_text"],
        analysis_attempts=row["analysis_attempts"],
        analysis_error=row["analysis_error"],
        analysis_attempted_at=_from_db(row["analysis_attempted_at"]),
        analysis_basis=(
            None
            if row["analysis_basis"] is None
            else AnalysisBasis(row["analysis_basis"])
        ),
    )


class ArticleRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, article: NewArticle) -> Article | None:
        """Store a new article; return ``None`` if its URL is already stored.

        Existing articles are never overwritten. A new article starts with the
        feed excerpt as its analysis basis.
        """
        normalized_url = normalize_url(article.url)
        with transaction(self._conn):
            row = fetch_one(
                self._conn,
                """
                INSERT INTO articles
                    (source, url, normalized_url, title, content,
                     published_at, collected_at, feed_id, analysis_basis)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    article.feed_id,
                    AnalysisBasis.EXCERPT,
                ),
            )
        return None if row is None else _row_to_article(row)

    def set_full_text(self, article_id: int, full_text: str) -> None:
        """Store the extracted page text and make it the analysis basis."""
        with transaction(self._conn):
            self._conn.execute(
                "UPDATE articles SET full_text = ?, analysis_basis = ? WHERE id = ?",
                (full_text, AnalysisBasis.FULL_TEXT, article_id),
            )

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

    # --- Analysis status (see ai_radar.analysis.pipeline) -----------------

    def claim_for_analysis(
        self, limit: int, max_attempts: int, now: datetime, retry_before: datetime
    ) -> list[Article]:
        """Atomically move up to ``limit`` articles to ``processing``.

        Candidates are ``new`` articles and ``failed`` ones with fewer than
        ``max_attempts`` attempts whose last attempt was claimed before
        ``retry_before``. The selection and update run in one write
        transaction, so concurrent callers never claim the same article.
        """
        with transaction(self._conn):
            rows = self._conn.execute(
                """
                UPDATE articles
                SET status = 'processing', analysis_attempted_at = ?
                WHERE id IN (
                    SELECT id FROM articles
                    WHERE status = 'new'
                       OR (status = 'failed'
                           AND analysis_attempts < ?
                           AND (analysis_attempted_at IS NULL
                                OR analysis_attempted_at < ?))
                    ORDER BY id
                    LIMIT ?
                )
                RETURNING *
                """,
                (_to_db(now), max_attempts, _to_db(retry_before), limit),
            ).fetchall()
        return sorted((_row_to_article(row) for row in rows), key=lambda a: a.id)

    def mark_analyzed(
        self, article_id: int, *, finished_at: datetime | None = None
    ) -> None:
        self._finish_attempt(
            article_id, ArticleStatus.ANALYZED, None, finished_at=finished_at
        )

    def mark_failed(
        self,
        article_id: int,
        error: str,
        *,
        count_attempt: bool = True,
        finished_at: datetime | None = None,
    ) -> None:
        """Record a failure; ``error`` must already be safe to show.

        With ``count_attempt=False`` (e.g. budget exhausted) the attempt does
        not count towards the maximum number of attempts.
        """
        self._finish_attempt(
            article_id,
            ArticleStatus.FAILED,
            error[:MAX_ANALYSIS_ERROR_LENGTH],
            count_attempt=count_attempt,
            finished_at=finished_at,
        )

    def reset_interrupted(self) -> int:
        """Return articles left in ``processing`` (e.g. after a crash) to ``new``.

        Only safe while no analysis is running; call it at startup.
        """
        with transaction(self._conn):
            cursor = self._conn.execute(
                "UPDATE articles SET status = 'new' WHERE status = 'processing'"
            )
        return cursor.rowcount

    def _finish_attempt(
        self,
        article_id: int,
        status: ArticleStatus,
        error: str | None,
        *,
        count_attempt: bool = True,
        finished_at: datetime | None = None,
    ) -> None:
        # analysis_attempted_at moves to the end of the attempt, so polling
        # clients (``since``) see the status change.
        finished = _to_db(finished_at or datetime.now(UTC))
        with transaction(self._conn):
            self._conn.execute(
                """
                UPDATE articles
                SET status = ?, analysis_error = ?,
                    analysis_attempts = analysis_attempts + ?,
                    analysis_attempted_at = ?
                WHERE id = ? AND status = 'processing'
                """,
                (status, error, 1 if count_attempt else 0, finished, article_id),
            )

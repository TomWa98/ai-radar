"""Database access for article feedback.

Each article has at most one rating. Setting or removing feedback never
touches stored analyses; learned preferences are derived from the feedback
separately (D6).
"""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from ai_radar.db import fetch_one, transaction

Clock = Callable[[], datetime]


class Rating(StrEnum):
    RELEVANT = "relevant"
    IRRELEVANT = "irrelevant"


@dataclass(frozen=True, slots=True)
class Feedback:
    article_id: int
    rating: Rating
    created_at: datetime
    updated_at: datetime


def _now() -> datetime:
    return datetime.now(UTC)


def _row_to_feedback(row: sqlite3.Row) -> Feedback:
    return Feedback(
        article_id=row["article_id"],
        rating=Rating(row["rating"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class FeedbackRepository:
    def __init__(self, conn: sqlite3.Connection, clock: Clock = _now) -> None:
        self._conn = conn
        self._clock = clock

    def _article_exists(self, article_id: int) -> bool:
        row = fetch_one(
            self._conn, "SELECT 1 FROM articles WHERE id = ?", (article_id,)
        )
        return row is not None

    def set(self, article_id: int, rating: Rating) -> Feedback | None:
        """Set or change the rating; return ``None`` if the article is unknown."""
        now = self._clock().astimezone(UTC).isoformat()
        with transaction(self._conn):
            if not self._article_exists(article_id):
                return None
            row = fetch_one(
                self._conn,
                """
                INSERT INTO article_feedback
                    (article_id, rating, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (article_id) DO UPDATE
                    SET rating = excluded.rating, updated_at = excluded.updated_at
                RETURNING *
                """,
                (article_id, Rating(rating), now, now),
            )
        assert row is not None
        return _row_to_feedback(row)

    def get(self, article_id: int) -> Feedback | None:
        row = fetch_one(
            self._conn,
            "SELECT * FROM article_feedback WHERE article_id = ?",
            (article_id,),
        )
        return None if row is None else _row_to_feedback(row)

    def remove(self, article_id: int) -> bool:
        """Remove the rating; return ``False`` if the article is unknown.

        Removing feedback that does not exist succeeds (idempotent).
        """
        with transaction(self._conn):
            if not self._article_exists(article_id):
                return False
            self._conn.execute(
                "DELETE FROM article_feedback WHERE article_id = ?", (article_id,)
            )
        return True

"""Database access for feeds.

Feed URLs are user input: they are validated here but never fetched.
"""

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

from ai_radar.articles.url import normalize_url
from ai_radar.db import fetch_one, transaction
from ai_radar.feeds.models import Feed, NewFeed

Clock = Callable[[], datetime]


class DuplicateFeedError(Exception):
    """Another feed with an equivalent URL already exists."""


def _now() -> datetime:
    return datetime.now(UTC)


def _to_db(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _row_to_feed(row: sqlite3.Row) -> Feed:
    return Feed(
        id=row["id"],
        url=row["url"],
        normalized_url=row["normalized_url"],
        name=row["name"],
        enabled=bool(row["enabled"]),
        fetch_full_text=bool(row["fetch_full_text"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _is_unique_violation(exc: sqlite3.IntegrityError) -> bool:
    return exc.sqlite_errorname == "SQLITE_CONSTRAINT_UNIQUE"


class FeedRepository:
    def __init__(self, conn: sqlite3.Connection, clock: Clock = _now) -> None:
        self._conn = conn
        self._clock = clock

    def add(self, feed: NewFeed) -> Feed:
        """Store a new feed.

        Raises ``ValueError`` for an unacceptable URL and
        :class:`DuplicateFeedError` if an equivalent URL is already stored; the
        existing feed is left unchanged.
        """
        url = feed.url.strip()
        normalized_url = normalize_url(url)
        now = _to_db(self._clock())
        with transaction(self._conn):
            row = fetch_one(
                self._conn,
                """
                INSERT INTO feeds
                    (url, normalized_url, name, enabled, fetch_full_text,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (normalized_url) DO NOTHING
                RETURNING *
                """,
                (
                    url,
                    normalized_url,
                    feed.name,
                    feed.enabled,
                    feed.fetch_full_text,
                    now,
                    now,
                ),
            )
        if row is None:
            raise DuplicateFeedError(f"Feed already exists: {normalized_url}")
        return _row_to_feed(row)

    def get_by_id(self, feed_id: int) -> Feed | None:
        row = fetch_one(self._conn, "SELECT * FROM feeds WHERE id = ?", (feed_id,))
        return None if row is None else _row_to_feed(row)

    def list_all(self) -> list[Feed]:
        rows = self._conn.execute("SELECT * FROM feeds ORDER BY id").fetchall()
        return [_row_to_feed(row) for row in rows]

    def update(self, feed_id: int, feed: NewFeed) -> Feed | None:
        """Replace the editable fields of a feed; return ``None`` if it is unknown.

        Raises the same errors as :meth:`add`; on error nothing is changed.
        """
        url = feed.url.strip()
        normalized_url = normalize_url(url)
        try:
            with transaction(self._conn):
                row = fetch_one(
                    self._conn,
                    """
                    UPDATE feeds
                    SET url = ?, normalized_url = ?, name = ?, enabled = ?,
                        fetch_full_text = ?, updated_at = ?
                    WHERE id = ?
                    RETURNING *
                    """,
                    (
                        url,
                        normalized_url,
                        feed.name,
                        feed.enabled,
                        feed.fetch_full_text,
                        _to_db(self._clock()),
                        feed_id,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if _is_unique_violation(exc):
                raise DuplicateFeedError(
                    f"Feed already exists: {normalized_url}"
                ) from exc
            raise
        return None if row is None else _row_to_feed(row)

    def remove(self, feed_id: int) -> bool:
        """Delete a feed; return ``False`` if it is unknown.

        Articles collected from the feed are kept.
        """
        with transaction(self._conn):
            row = fetch_one(
                self._conn, "DELETE FROM feeds WHERE id = ? RETURNING id", (feed_id,)
            )
        return row is not None

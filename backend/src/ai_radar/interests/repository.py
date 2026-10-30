"""Database access for manual interests.

Manual interests are only ever changed through this repository's explicit
add/update/remove calls (i.e. by the user); nothing changes them
automatically. Learned preferences are stored separately (D6).
"""

import sqlite3
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from ai_radar.analysis.models import Interest, InterestWeight
from ai_radar.db import fetch_one, transaction

MAX_TOPIC_LENGTH = 100
# Interests are passed to the analyzer with every article; bound their number.
MAX_INTERESTS = 100

Clock = Callable[[], datetime]


class DuplicateInterestError(Exception):
    """Another interest has the same topic (ignoring case and spacing)."""


class TooManyInterestsError(Exception):
    """The maximum number of interests is reached."""


def normalize_topic(topic: str) -> str:
    """Collapse whitespace; raise ``ValueError`` for an unusable topic."""
    topic = " ".join(topic.split())
    if not topic:
        raise ValueError("Topic must not be empty")
    if len(topic) > MAX_TOPIC_LENGTH:
        raise ValueError(f"Topic must be at most {MAX_TOPIC_LENGTH} characters")
    if any(unicodedata.category(char).startswith("C") for char in topic):
        raise ValueError("Topic must not contain control characters")
    return topic


def topic_key(topic: str) -> str:
    return normalize_topic(topic).casefold()


@dataclass(frozen=True, slots=True)
class StoredInterest:
    id: int
    topic: str
    weight: InterestWeight
    created_at: datetime
    updated_at: datetime

    def as_input(self) -> Interest:
        return Interest(topic=self.topic, weight=self.weight)


def _now() -> datetime:
    return datetime.now(UTC)


def _row_to_interest(row: sqlite3.Row) -> StoredInterest:
    return StoredInterest(
        id=row["id"],
        topic=row["topic"],
        weight=InterestWeight(row["weight"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class InterestRepository:
    def __init__(self, conn: sqlite3.Connection, clock: Clock = _now) -> None:
        self._conn = conn
        self._clock = clock

    def add(self, topic: str, weight: InterestWeight) -> StoredInterest:
        """Store a new interest.

        Raises ``ValueError`` for an unusable topic, :class:`DuplicateInterestError`
        if the topic exists, and :class:`TooManyInterestsError` at the limit.
        """
        topic = normalize_topic(topic)
        now = self._clock().astimezone(UTC).isoformat()
        with transaction(self._conn):
            count = fetch_one(self._conn, "SELECT COUNT(*) FROM interests")
            assert count is not None
            if count[0] >= MAX_INTERESTS:
                raise TooManyInterestsError(
                    f"At most {MAX_INTERESTS} interests are allowed"
                )
            row = fetch_one(
                self._conn,
                """
                INSERT INTO interests (topic, topic_key, weight, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (topic_key) DO NOTHING
                RETURNING *
                """,
                (topic, topic.casefold(), InterestWeight(weight), now, now),
            )
        if row is None:
            raise DuplicateInterestError("An interest with this topic already exists")
        return _row_to_interest(row)

    def get(self, interest_id: int) -> StoredInterest | None:
        row = fetch_one(
            self._conn, "SELECT * FROM interests WHERE id = ?", (interest_id,)
        )
        return None if row is None else _row_to_interest(row)

    def list_all(self) -> list[StoredInterest]:
        rows = self._conn.execute("SELECT * FROM interests ORDER BY id").fetchall()
        return [_row_to_interest(row) for row in rows]

    def update(
        self,
        interest_id: int,
        *,
        topic: str | None = None,
        weight: InterestWeight | None = None,
    ) -> StoredInterest | None:
        """Change the given fields; return ``None`` if the interest is unknown.

        Reading and writing happen in one transaction, so concurrent updates
        of different fields do not overwrite each other.
        """
        if topic is not None:
            topic = normalize_topic(topic)
        try:
            with transaction(self._conn):
                current = self.get(interest_id)
                if current is None:
                    return None
                new_topic = current.topic if topic is None else topic
                row = fetch_one(
                    self._conn,
                    """
                    UPDATE interests
                    SET topic = ?, topic_key = ?, weight = ?, updated_at = ?
                    WHERE id = ?
                    RETURNING *
                    """,
                    (
                        new_topic,
                        new_topic.casefold(),
                        InterestWeight(weight or current.weight),
                        self._clock().astimezone(UTC).isoformat(),
                        interest_id,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if exc.sqlite_errorname == "SQLITE_CONSTRAINT_UNIQUE":
                raise DuplicateInterestError(
                    "An interest with this topic already exists"
                ) from exc
            raise
        assert row is not None
        return _row_to_interest(row)

    def remove(self, interest_id: int) -> bool:
        with transaction(self._conn):
            row = fetch_one(
                self._conn,
                "DELETE FROM interests WHERE id = ? RETURNING id",
                (interest_id,),
            )
        return row is not None

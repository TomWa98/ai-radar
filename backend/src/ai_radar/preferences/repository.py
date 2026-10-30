"""Learned preferences: a simple, rule-based heuristic without machine learning.

The rule (D6, see ``docs/architecture.md``):

* Every rated article contributes the topic keywords of its latest analysis.
* Per topic, each "relevant" rating counts +1 and each "irrelevant" -1.
* A topic becomes a learned preference once at least three rated articles
  carry it. Its score is the sum; the counts explain it.

Learned preferences are computed from the stored feedback when needed and are
kept apart from the manual interests. A reset records a timestamp: only
feedback given or changed afterwards counts, so the reset deletes neither
feedback nor manual interests. Preferences only influence new analyses;
existing analyses are never recomputed.
"""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from ai_radar.analysis.models import LearnedPreference
from ai_radar.db import fetch_one, transaction

MIN_RATINGS = 3
# Learned preferences are sent with every analysis; pass the strongest ones.
MAX_FOR_ANALYSIS = 50

Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class LearnedTopic:
    topic: str
    score: int  # relevant - irrelevant
    relevant: int
    irrelevant: int

    @property
    def ratings(self) -> int:
        return self.relevant + self.irrelevant

    def as_input(self) -> LearnedPreference:
        return LearnedPreference(topic=self.topic, score=self.score)


def _now() -> datetime:
    return datetime.now(UTC)


class PreferenceRepository:
    def __init__(self, conn: sqlite3.Connection, clock: Clock = _now) -> None:
        self._conn = conn
        self._clock = clock

    def last_reset_at(self) -> datetime | None:
        row = fetch_one(self._conn, "SELECT MAX(reset_at) FROM preference_resets")
        return None if row is None or row[0] is None else datetime.fromisoformat(row[0])

    def learned(self) -> list[LearnedTopic]:
        """All learned preferences, strongest (by absolute score) first."""
        reset_at = self.last_reset_at()
        rows = self._conn.execute(
            """
            WITH latest AS (
                SELECT article_id, MAX(id) AS id FROM analyses GROUP BY article_id
            )
            SELECT topic.value AS topic,
                   SUM(f.rating = 'relevant') AS relevant,
                   SUM(f.rating = 'irrelevant') AS irrelevant
            FROM article_feedback AS f
            JOIN latest ON latest.article_id = f.article_id
            JOIN analyses AS a ON a.id = latest.id,
                 json_each(a.topics) AS topic
            WHERE f.updated_at > ?
            GROUP BY topic.value
            HAVING COUNT(*) >= ?
            """,
            (
                "" if reset_at is None else reset_at.astimezone(UTC).isoformat(),
                MIN_RATINGS,
            ),
        ).fetchall()
        topics = [
            LearnedTopic(
                topic=row["topic"],
                score=row["relevant"] - row["irrelevant"],
                relevant=row["relevant"],
                irrelevant=row["irrelevant"],
            )
            for row in rows
        ]
        return sorted(topics, key=lambda t: (-abs(t.score), t.topic))

    def for_analysis(self) -> tuple[LearnedPreference, ...]:
        """The strongest learned preferences as analyzer input."""
        return tuple(t.as_input() for t in self.learned()[:MAX_FOR_ANALYSIS])

    def reset(self) -> datetime:
        """Forget all learned preferences; feedback and interests stay."""
        reset_at = self._clock().astimezone(UTC)
        with transaction(self._conn):
            self._conn.execute(
                "INSERT INTO preference_resets (reset_at) VALUES (?)",
                (reset_at.isoformat(),),
            )
        return reset_at

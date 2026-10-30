"""Ledger of paid LLM calls: tokens and estimated cost per call (D5).

The monthly total (UTC calendar month) is what the budget is checked
against. Every operation opens its own connection, so the ledger can be used
from the analysis worker threads.
"""

from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from ai_radar.analysis.models import Usage
from ai_radar.db import connect, fetch_one, transaction

Clock = Callable[[], datetime]


def _now() -> datetime:
    return datetime.now(UTC)


def month_start(moment: datetime) -> datetime:
    """Start of the UTC calendar month containing ``moment``."""
    return moment.astimezone(UTC).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )


class UsageLedger:
    def __init__(self, db_path: Path, clock: Clock = _now) -> None:
        self._db_path = db_path
        self._clock = clock

    def record(self, usage: Usage) -> None:
        with closing(connect(self._db_path)) as conn, transaction(conn):
            conn.execute(
                """
                INSERT INTO llm_calls
                    (called_at, model, input_tokens, output_tokens, estimated_cost)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    self._clock().astimezone(UTC).isoformat(),
                    usage.model,
                    usage.input_tokens,
                    usage.output_tokens,
                    usage.estimated_cost,
                ),
            )

    def spent_this_month(self) -> float:
        start = month_start(self._clock()).isoformat()
        with closing(connect(self._db_path)) as conn:
            row = fetch_one(
                conn,
                "SELECT COALESCE(SUM(estimated_cost), 0) FROM llm_calls "
                "WHERE called_at >= ?",
                (start,),
            )
        assert row is not None
        return float(row[0])

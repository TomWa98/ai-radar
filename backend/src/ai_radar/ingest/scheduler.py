"""Periodic ingestion of the stored feeds inside the API process (D2).

One background task in the FastAPI lifespan runs a pass every interval. Each
pass runs in a worker thread (``asyncio.to_thread``) so blocking network and
SQLite calls never stall the event loop. :class:`IngestionRunner` ensures that
at most one pass runs at a time, whether scheduled or started manually
(``POST /api/refresh``).

On shutdown the task is cancelled. A pass that is already running in its
worker thread cannot be interrupted; it finishes on its own, bounded by the
per-feed fetch timeouts.
"""

import asyncio
import logging
import math
import threading
from collections.abc import Awaitable, Callable
from contextlib import ExitStack, closing
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from ai_radar.articles.repository import ArticleRepository
from ai_radar.db import connect
from ai_radar.feeds.repository import FeedRepository
from ai_radar.ingest.fetch import create_client, fetch_feed, fetch_page
from ai_radar.ingest.fulltext import PageFetcher
from ai_radar.ingest.service import FeedResult, Fetcher, ingest_stored_feeds

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_MINUTES = 15.0

Sleep = Callable[[float], Awaitable[object]]
Clock = Callable[[], datetime]


def _now() -> datetime:
    return datetime.now(UTC)


def fetch_interval_seconds(minutes: str | None) -> float | None:
    """Parse the configured interval in minutes; ``None`` means disabled.

    An unset value uses the default; ``0`` disables the scheduler. Raises
    ``ValueError`` for anything else that is not a positive number.
    """
    if minutes is None or not minutes.strip():
        return DEFAULT_INTERVAL_MINUTES * 60
    try:
        value = float(minutes)
    except ValueError:
        raise ValueError(f"Invalid fetch interval: {minutes!r}") from None
    if value == 0:
        return None
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"Invalid fetch interval: {minutes!r}")
    return value * 60


def ingest_stored_feeds_once(
    db_path: Path,
    fetch: Fetcher | None = None,
    page_fetch: PageFetcher | None = None,
) -> list[FeedResult]:
    """Run one ingestion pass over the stored feeds with its own connection."""
    with ExitStack() as stack:
        conn = stack.enter_context(closing(connect(db_path)))
        if fetch is None or page_fetch is None:
            client = stack.enter_context(create_client())
            if fetch is None:
                fetch = partial(fetch_feed, client=client)
            if page_fetch is None:
                page_fetch = partial(fetch_page, client=client)
        return ingest_stored_feeds(
            FeedRepository(conn),
            fetch,
            ArticleRepository(conn),
            fetch_page=page_fetch,
        )


@dataclass(frozen=True, slots=True)
class RunStatus:
    running: bool
    last_started_at: datetime | None
    last_finished_at: datetime | None


class IngestionRunner:
    """Runs ingestion passes, never more than one at a time."""

    def __init__(self, run: Callable[[], object], clock: Clock = _now) -> None:
        self._run = run
        self._clock = clock
        self._lock = threading.Lock()  # held for the whole pass
        self._state = threading.Lock()  # guards the fields below
        self._running = False
        self._started_at: datetime | None = None
        self._finished_at: datetime | None = None
        self._idle = threading.Event()
        self._idle.set()

    def try_run(self) -> bool:
        """Run one pass; return ``False`` without running if one is in progress.

        Exceptions from the pass propagate to the caller.
        """
        if not self._lock.acquire(blocking=False):
            return False
        self._begin()
        try:
            self._run()
        finally:
            self._end()
        return True

    def try_start(self) -> bool:
        """Start one pass in a background thread and return immediately.

        Returns ``False`` without starting if a pass is in progress. Exceptions
        from the pass are logged (type only).
        """
        if not self._lock.acquire(blocking=False):
            return False
        self._begin()
        try:
            threading.Thread(
                target=self._run_in_background, name="manual-ingestion", daemon=True
            ).start()
        except BaseException:
            self._end()
            raise
        return True

    def status(self) -> RunStatus:
        with self._state:
            return RunStatus(self._running, self._started_at, self._finished_at)

    def wait_until_idle(self, timeout: float | None = None) -> bool:
        """Block until no pass is running; return ``False`` on timeout."""
        return self._idle.wait(timeout)

    def _run_in_background(self) -> None:
        try:
            self._run()
        except Exception as exc:
            # Only the type: the message may contain untrusted detail.
            logger.error("Manual ingestion failed: %s", type(exc).__name__)
        finally:
            self._end()

    def _begin(self) -> None:
        with self._state:
            self._running = True
            self._started_at = self._clock()
            self._idle.clear()

    def _end(self) -> None:
        with self._state:
            self._running = False
            self._finished_at = self._clock()
        self._lock.release()
        self._idle.set()


async def run_periodically(
    runner: IngestionRunner, interval: float, sleep: Sleep = asyncio.sleep
) -> None:
    """Run a pass now and then every ``interval`` seconds until cancelled.

    A failing pass is logged and the schedule continues.
    """
    while True:
        try:
            if not await asyncio.to_thread(runner.try_run):
                logger.info("Scheduled ingestion skipped: a pass is still running")
        except Exception as exc:
            # Only the type: the message may contain untrusted detail.
            logger.error("Scheduled ingestion failed: %s", type(exc).__name__)
        await sleep(interval)

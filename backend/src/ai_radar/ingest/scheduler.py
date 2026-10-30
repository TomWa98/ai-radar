"""Periodic ingestion of the stored feeds inside the API process (D2).

One background task in the FastAPI lifespan runs a pass every interval. Each
pass runs in a worker thread (``asyncio.to_thread``) so blocking network and
SQLite calls never stall the event loop. :class:`IngestionRunner` ensures that
at most one pass runs at a time.

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
from functools import partial
from pathlib import Path

from ai_radar.articles.repository import ArticleRepository
from ai_radar.db import connect
from ai_radar.feeds.repository import FeedRepository
from ai_radar.ingest.fetch import create_client, fetch_feed
from ai_radar.ingest.service import FeedResult, Fetcher, ingest_stored_feeds

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_MINUTES = 15.0

Sleep = Callable[[float], Awaitable[object]]


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
    db_path: Path, fetch: Fetcher | None = None
) -> list[FeedResult]:
    """Run one ingestion pass over the stored feeds with its own connection."""
    with ExitStack() as stack:
        conn = stack.enter_context(closing(connect(db_path)))
        if fetch is None:
            client = stack.enter_context(create_client())
            fetch = partial(fetch_feed, client=client)
        return ingest_stored_feeds(FeedRepository(conn), fetch, ArticleRepository(conn))


class IngestionRunner:
    """Runs ingestion passes, never more than one at a time."""

    def __init__(self, run: Callable[[], object]) -> None:
        self._run = run
        self._lock = threading.Lock()

    def try_run(self) -> bool:
        """Run one pass; return ``False`` without running if one is in progress."""
        if not self._lock.acquire(blocking=False):
            return False
        try:
            self._run()
        finally:
            self._lock.release()
        return True


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

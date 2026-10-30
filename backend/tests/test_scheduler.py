import asyncio
import logging
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_radar.db import open_database
from ai_radar.feeds.models import NewFeed
from ai_radar.feeds.repository import FeedRepository
from ai_radar.ingest.fetch import FetchedFeed, FetchError
from ai_radar.ingest.scheduler import (
    IngestionRunner,
    RunStatus,
    fetch_interval_seconds,
    ingest_stored_feeds_once,
    run_periodically,
)
from ai_radar.main import DB_PATH_ENV, FETCH_INTERVAL_ENV, app

FEED = b"""<rss version="2.0"><channel><title>Feed</title>
  <item><title>One</title><link>https://example.com/1</link></item>
</channel></rss>"""


class FakeSleep:
    """Records requested sleeps; cancels the loop after ``rounds`` sleeps."""

    def __init__(self, rounds: int) -> None:
        self.rounds = rounds
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        if len(self.calls) >= self.rounds:
            raise asyncio.CancelledError


def run_loop(runner: IngestionRunner, sleep: FakeSleep, interval: float = 900) -> None:
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run_periodically(runner, interval, sleep))


# --- Configuration -------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "seconds"),
    [(None, 900.0), ("", 900.0), ("15", 900.0), ("0.5", 30.0), ("0", None)],
)
def test_fetch_interval(value: str | None, seconds: float | None) -> None:
    assert fetch_interval_seconds(value) == seconds


@pytest.mark.parametrize("value", ["-1", "abc", "nan", "inf"])
def test_invalid_fetch_interval(value: str) -> None:
    with pytest.raises(ValueError, match="Invalid fetch interval"):
        fetch_interval_seconds(value)


# --- Loop --------------------------------------------------------------------


def test_runs_immediately_and_then_every_interval() -> None:
    runs: list[int] = []
    sleep = FakeSleep(rounds=3)

    run_loop(IngestionRunner(lambda: runs.append(1)), sleep, interval=60)

    assert len(runs) == 3
    assert sleep.calls == [60, 60, 60]


def test_pass_runs_outside_event_loop_thread() -> None:
    threads: list[threading.Thread] = []

    run_loop(
        IngestionRunner(lambda: threads.append(threading.current_thread())),
        FakeSleep(rounds=1),
    )

    assert threads and threads[0] is not threading.main_thread()


def test_failing_pass_does_not_stop_scheduler(
    caplog: pytest.LogCaptureFixture,
) -> None:
    runs: list[int] = []

    def flaky() -> None:
        runs.append(1)
        if len(runs) == 1:
            raise RuntimeError("secret detail")

    with caplog.at_level(logging.ERROR):
        run_loop(IngestionRunner(flaky), FakeSleep(rounds=2))

    assert len(runs) == 2
    assert "Scheduled ingestion failed: RuntimeError" in caplog.text
    assert "secret detail" not in caplog.text


def test_runner_lock_is_released_after_failure() -> None:
    def fail() -> None:
        raise RuntimeError

    runner = IngestionRunner(fail)
    with pytest.raises(RuntimeError):
        runner.try_run()
    with pytest.raises(RuntimeError):
        runner.try_run()  # not blocked by a leaked lock


def test_overlapping_pass_is_skipped(caplog: pytest.LogCaptureFixture) -> None:
    started = threading.Event()
    release = threading.Event()
    runs: list[int] = []

    def slow() -> None:
        runs.append(1)
        started.set()
        release.wait(5)

    runner = IngestionRunner(slow)
    first = threading.Thread(target=runner.try_run)
    first.start()
    try:
        assert started.wait(5)
        assert runner.try_run() is False  # e.g. a manual refresh
        with caplog.at_level(logging.INFO):
            run_loop(runner, FakeSleep(rounds=1))
    finally:
        release.set()
        first.join()

    assert len(runs) == 1
    assert "skipped" in caplog.text
    assert runner.try_run() is True  # free again afterwards


# --- One pass ----------------------------------------------------------------


def test_ingest_stored_feeds_once(tmp_path: Path) -> None:
    db = tmp_path / "radar.db"
    with open_database(db) as conn:
        feeds = FeedRepository(conn)
        ok = feeds.add(NewFeed(url="https://a.example/rss"))
        down = feeds.add(NewFeed(url="https://down.example/rss"))

    def fetch(url: str) -> FetchedFeed:
        if url == down.url:
            raise FetchError("HTTP status 503")
        return FetchedFeed(FEED, url)

    results = ingest_stored_feeds_once(db, fetch)

    assert [r.ok for r in results] == [True, False]
    with open_database(db) as conn:
        feeds = FeedRepository(conn)
        stored_ok = feeds.get_by_id(ok.id)
        stored_down = feeds.get_by_id(down.id)
    assert stored_ok is not None and stored_ok.last_success_at is not None
    assert stored_down is not None and stored_down.last_error == "HTTP status 503"


# --- Lifespan ----------------------------------------------------------------


@pytest.fixture
def db_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "api.db"
    monkeypatch.setenv(DB_PATH_ENV, str(path))
    return path


def test_lifespan_starts_and_stops_scheduler(
    db_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(FETCH_INTERVAL_ENV, "15")
    passes = threading.Event()
    monkeypatch.setattr(
        "ai_radar.main.ingest_stored_feeds_once",
        lambda db_path: passes.set(),
    )

    with TestClient(app, base_url="http://127.0.0.1"):
        task = app.state.scheduler
        assert task is not None and not task.done()
        assert passes.wait(5)  # first pass runs right after startup

    assert task.cancelled()


def test_scheduler_can_be_disabled(db_env: Path) -> None:
    with TestClient(app, base_url="http://127.0.0.1"):
        assert app.state.scheduler is None
        assert isinstance(app.state.ingestion, IngestionRunner)


def test_invalid_interval_fails_startup(
    db_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(FETCH_INTERVAL_ENV, "soon")

    with pytest.raises(ValueError, match="Invalid fetch interval"):
        with TestClient(app, base_url="http://127.0.0.1"):
            pass


# --- Manual start and status -------------------------------------------------


class StepClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        current = self.now
        self.now += timedelta(minutes=1)
        return current


def test_try_start_runs_in_background_and_records_status() -> None:
    started = threading.Event()
    release = threading.Event()
    clock = StepClock()

    def slow() -> None:
        started.set()
        release.wait(5)

    runner = IngestionRunner(slow, clock)
    assert runner.status() == RunStatus(False, None, None)

    assert runner.try_start() is True  # returns before the pass finishes
    assert started.wait(5)
    running = runner.status()
    assert running.running is True
    assert running.last_started_at == datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
    assert running.last_finished_at is None

    release.set()
    assert runner.wait_until_idle(5)
    done = runner.status()
    assert done.running is False
    assert done.last_started_at == running.last_started_at
    assert done.last_finished_at == datetime(2026, 10, 30, 12, 1, tzinfo=UTC)


def test_manual_and_scheduled_passes_share_the_lock() -> None:
    release = threading.Event()
    runs: list[int] = []

    def slow() -> None:
        runs.append(1)
        release.wait(5)

    runner = IngestionRunner(slow)
    try:
        assert runner.try_start() is True
        assert runner.try_start() is False
        assert runner.try_run() is False
    finally:
        release.set()
    assert runner.wait_until_idle(5)
    assert runs == [1]
    assert runner.try_run() is True  # scheduled pass after the manual one


def test_failing_background_pass_is_logged_and_releases_lock(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail() -> None:
        raise RuntimeError("secret detail")

    runner = IngestionRunner(fail)
    with caplog.at_level(logging.ERROR):
        assert runner.try_start() is True
        assert runner.wait_until_idle(5)

    assert "Manual ingestion failed: RuntimeError" in caplog.text
    assert "secret detail" not in caplog.text
    status = runner.status()
    assert status.running is False and status.last_finished_at is not None
    assert runner.try_start() is True
    assert runner.wait_until_idle(5)


def test_failed_thread_start_releases_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_start(self: threading.Thread) -> None:
        raise RuntimeError("can't start new thread")

    runner = IngestionRunner(lambda: None)
    monkeypatch.setattr(threading.Thread, "start", broken_start)
    with pytest.raises(RuntimeError):
        runner.try_start()
    monkeypatch.undo()

    assert runner.status().running is False
    assert runner.try_run() is True

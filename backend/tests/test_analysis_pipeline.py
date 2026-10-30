import logging
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_radar.analysis.analyzer import AnalysisError, FakeAnalyzer
from ai_radar.analysis.models import AnalysisInput, AnalysisResult
from ai_radar.analysis.pipeline import (
    AnalysisSettings,
    PipelineStats,
    analyze_pending,
)
from ai_radar.analysis.repository import AnalysisRepository
from ai_radar.articles.models import AnalysisBasis, ArticleStatus, NewArticle
from ai_radar.articles.repository import ArticleRepository
from ai_radar.db import connect, open_database
from ai_radar.feeds.models import NewFeed
from ai_radar.feeds.repository import FeedRepository
from ai_radar.ingest.fetch import FetchedFeed
from ai_radar.ingest.scheduler import ingest_and_analyze_once
from ai_radar.main import DB_PATH_ENV, app

T0 = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
SECRET_TEXT = "CONFIDENTIAL ARTICLE BODY"


class StepClock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        current = self.now
        self.now += timedelta(seconds=1)
        return current


class ScriptedAnalyzer:
    """Fails for titles listed in ``failures``; otherwise behaves like Fake."""

    def __init__(self, failures: dict[str, Exception] | None = None) -> None:
        self.failures = failures or {}
        self.calls: list[str] = []
        self._lock = threading.Lock()

    def analyze(self, item: AnalysisInput) -> AnalysisResult:
        with self._lock:
            self.calls.append(item.title)
        if item.title in self.failures:
            raise self.failures[item.title]
        return FakeAnalyzer().analyze(item)


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with open_database(tmp_path / "test.db") as connection:
        yield connection


def add(conn: sqlite3.Connection, title: str, content: str | None = None) -> int:
    article = ArticleRepository(conn).add(
        NewArticle(
            source="Example",
            url=f"https://example.com/{title.replace(' ', '-')}",
            title=title,
            content=content if content is not None else f"Excerpt of {title}",
            published_at=None,
            collected_at=T0,
        )
    )
    assert article is not None
    return article.id


def status(conn: sqlite3.Connection, article_id: int) -> ArticleStatus:
    article = ArticleRepository(conn).get_by_id(article_id)
    assert article is not None
    return article.status


def run(
    conn: sqlite3.Connection,
    analyzer: object,
    clock: StepClock | None = None,
    **settings: int,
) -> PipelineStats:
    return analyze_pending(
        conn,
        analyzer,  # type: ignore[arg-type]
        AnalysisSettings(**settings),  # type: ignore[arg-type]
        clock=clock or StepClock(),
    )


# --- Settings ------------------------------------------------------------


def test_default_settings_use_fake_analyzer(tmp_path: Path) -> None:
    settings = AnalysisSettings.from_env({})
    assert settings == AnalysisSettings("fake", 3, 2)
    assert isinstance(settings.create_analyzer(tmp_path / "x.db"), FakeAnalyzer)


def test_settings_from_env() -> None:
    settings = AnalysisSettings.from_env(
        {
            "AI_RADAR_ANALYZER": " Fake ",
            "AI_RADAR_ANALYSIS_MAX_ATTEMPTS": "5",
            "AI_RADAR_ANALYSIS_CONCURRENCY": "4",
        }
    )
    assert settings == AnalysisSettings("fake", 5, 4)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("AI_RADAR_ANALYZER", "gpt"),
        ("AI_RADAR_ANALYSIS_MAX_ATTEMPTS", "0"),
        ("AI_RADAR_ANALYSIS_MAX_ATTEMPTS", "many"),
        ("AI_RADAR_ANALYSIS_CONCURRENCY", "-2"),
    ],
)
def test_invalid_settings_are_rejected(name: str, value: str) -> None:
    with pytest.raises(ValueError):
        AnalysisSettings.from_env({name: value})


# --- Pipeline ------------------------------------------------------------


def test_new_articles_are_analyzed(conn: sqlite3.Connection) -> None:
    ids = [add(conn, f"Article {i}") for i in range(3)]

    stats = run(conn, FakeAnalyzer())

    assert stats == PipelineStats(analyzed=3, failed=0)
    articles = ArticleRepository(conn)
    analyses = AnalysisRepository(conn)
    for article_id in ids:
        article = articles.get_by_id(article_id)
        assert article is not None
        assert article.status is ArticleStatus.ANALYZED
        assert (article.analysis_attempts, article.analysis_error) == (1, None)
        stored = analyses.latest_for_article(article_id)
        assert stored is not None and stored.result.basis is AnalysisBasis.EXCERPT
    assert run(conn, FakeAnalyzer()) == PipelineStats()  # nothing left to do


def test_full_text_is_used_when_available(conn: sqlite3.Connection) -> None:
    article_id = add(conn, "Long read")
    ArticleRepository(conn).set_full_text(article_id, "The full article text.")
    seen: list[AnalysisInput] = []

    class Recording:
        def analyze(self, item: AnalysisInput) -> AnalysisResult:
            seen.append(item)
            return FakeAnalyzer().analyze(item)

    run(conn, Recording())

    assert seen[0].text == "The full article text."
    assert seen[0].basis is AnalysisBasis.FULL_TEXT
    stored = AnalysisRepository(conn).latest_for_article(article_id)
    assert stored is not None and stored.result.basis is AnalysisBasis.FULL_TEXT


def test_failures_are_isolated_and_recorded(
    conn: sqlite3.Connection, caplog: pytest.LogCaptureFixture
) -> None:
    ok = add(conn, "Fine")
    expected = add(conn, "Expected failure")
    unexpected = add(conn, "Unexpected failure", content=SECRET_TEXT)
    analyzer = ScriptedAnalyzer(
        {
            "Expected failure": AnalysisError("Provider rejected the request"),
            "Unexpected failure": RuntimeError(f"api_key=sk-test {SECRET_TEXT}"),
        }
    )

    with caplog.at_level(logging.WARNING):
        stats = run(conn, analyzer)

    assert stats == PipelineStats(analyzed=1, failed=2)
    articles = ArticleRepository(conn)
    assert status(conn, ok) is ArticleStatus.ANALYZED
    first = articles.get_by_id(expected)
    second = articles.get_by_id(unexpected)
    assert first is not None and second is not None
    assert first.status is ArticleStatus.FAILED
    assert first.analysis_error == "Provider rejected the request"
    assert first.analysis_attempts == 1
    assert second.status is ArticleStatus.FAILED
    assert second.analysis_error == "Unexpected RuntimeError"
    for text in ("sk-test", SECRET_TEXT):
        assert text not in caplog.text
        assert text not in (second.analysis_error or "")
    assert AnalysisRepository(conn).latest_for_article(expected) is None


def test_invalid_result_fails_the_article(conn: sqlite3.Connection) -> None:
    article_id = add(conn, "Bad result")

    class Broken:
        def analyze(self, item: AnalysisInput) -> AnalysisResult:
            good = FakeAnalyzer().analyze(item).model_dump()
            return AnalysisResult.model_construct(**{**good, "importance": 9})

    run(conn, Broken())

    article = ArticleRepository(conn).get_by_id(article_id)
    assert article is not None and article.status is ArticleStatus.FAILED
    assert article.analysis_error == "Invalid analyzer result"


def test_basis_mismatch_fails_the_article(conn: sqlite3.Connection) -> None:
    article_id = add(conn, "Wrong basis")

    class Lying:
        def analyze(self, item: AnalysisInput) -> AnalysisResult:
            result = FakeAnalyzer().analyze(item)
            return result.model_copy(update={"basis": AnalysisBasis.FULL_TEXT})

    run(conn, Lying())

    article = ArticleRepository(conn).get_by_id(article_id)
    assert article is not None and article.status is ArticleStatus.FAILED
    assert article.analysis_error == "Analysis basis does not match the input"


def test_failed_articles_are_retried_up_to_max_attempts(
    conn: sqlite3.Connection,
) -> None:
    article_id = add(conn, "Flaky")
    analyzer = ScriptedAnalyzer({"Flaky": AnalysisError("Temporary error")})
    clock = StepClock()

    for _ in range(5):
        run(conn, analyzer, clock, max_attempts=3)

    assert analyzer.calls == ["Flaky"] * 3  # one attempt per pass, three in total
    article = ArticleRepository(conn).get_by_id(article_id)
    assert article is not None
    assert (article.status, article.analysis_attempts) == (ArticleStatus.FAILED, 3)


def test_retry_succeeds_later(conn: sqlite3.Connection) -> None:
    article_id = add(conn, "Flaky")
    clock = StepClock()
    run(conn, ScriptedAnalyzer({"Flaky": AnalysisError("Temporary")}), clock)

    stats = run(conn, ScriptedAnalyzer(), clock)

    assert stats == PipelineStats(analyzed=1, failed=0)
    article = ArticleRepository(conn).get_by_id(article_id)
    assert article is not None
    assert article.status is ArticleStatus.ANALYZED
    assert (article.analysis_attempts, article.analysis_error) == (2, None)


def test_concurrency_is_bounded(conn: sqlite3.Connection) -> None:
    for i in range(6):
        add(conn, f"Article {i}")
    active = 0
    peak = 0
    lock = threading.Lock()
    both_running = threading.Barrier(2, timeout=5)

    class Slow:
        def analyze(self, item: AnalysisInput) -> AnalysisResult:
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            try:
                both_running.wait()  # proves two calls really overlap
            except threading.BrokenBarrierError:
                pass
            with lock:
                active -= 1
            return FakeAnalyzer().analyze(item)

    stats = run(conn, Slow(), concurrency=2)

    assert stats.analyzed == 6
    assert peak == 2


def test_concurrent_claims_never_overlap(tmp_path: Path) -> None:
    path = tmp_path / "test.db"
    with open_database(path) as conn:
        for i in range(40):
            add(conn, f"Article {i}")
    claimed: list[list[int]] = []
    barrier = threading.Barrier(4)

    def claim() -> None:
        with closing(connect(path, timeout=5)) as conn:
            barrier.wait()
            batch = ArticleRepository(conn).claim_for_analysis(15, 3, T0, T0)
            claimed.append([article.id for article in batch])

    threads = [threading.Thread(target=claim) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    all_ids = [article_id for batch in claimed for article_id in batch]
    assert len(all_ids) == len(set(all_ids)) == 40


def test_interrupted_articles_are_reset(conn: sqlite3.Connection) -> None:
    article_id = add(conn, "Interrupted")
    articles = ArticleRepository(conn)
    articles.claim_for_analysis(10, 3, T0, T0)
    assert status(conn, article_id) is ArticleStatus.PROCESSING

    assert articles.reset_interrupted() == 1

    assert status(conn, article_id) is ArticleStatus.NEW
    assert run(conn, FakeAnalyzer()).analyzed == 1


def test_analyzed_articles_are_not_reanalyzed(conn: sqlite3.Connection) -> None:
    add(conn, "Done")
    analyzer = ScriptedAnalyzer()
    run(conn, analyzer)
    run(conn, analyzer)
    assert analyzer.calls == ["Done"]


# --- Integration with the fetch pass and the app ------------------------

FEED = b"""<rss version="2.0"><channel><title>Feed</title>
  <item><title>One</title><link>https://example.com/1</link>
    <description>First</description></item>
</channel></rss>"""


def test_fetch_pass_analyzes_new_articles(tmp_path: Path) -> None:
    db = tmp_path / "radar.db"
    with open_database(db) as conn:
        FeedRepository(conn).add(NewFeed(url="https://a.example/rss"))

    ingest_and_analyze_once(
        db,
        FakeAnalyzer(),
        AnalysisSettings(),
        lambda url: FetchedFeed(FEED, url),
        lambda url: FetchedFeed(b"", url),
    )

    with open_database(db) as conn:
        article = ArticleRepository(conn).get_by_url("https://example.com/1")
        assert article is not None and article.status is ArticleStatus.ANALYZED
        assert AnalysisRepository(conn).latest_for_article(article.id) is not None


def test_fetch_failure_does_not_block_analysis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "radar.db"
    with open_database(db) as conn:
        article_id = add(conn, "Already stored")

    def broken(*args: object) -> None:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr("ai_radar.ingest.scheduler.ingest_stored_feeds_once", broken)
    ingest_and_analyze_once(db, FakeAnalyzer(), AnalysisSettings())

    with open_database(db) as conn:
        assert status(conn, article_id) is ArticleStatus.ANALYZED


def test_startup_resets_interrupted_articles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "api.db"
    with open_database(db) as conn:
        article_id = add(conn, "Stuck")
        ArticleRepository(conn).claim_for_analysis(10, 3, T0, T0)
    monkeypatch.setenv(DB_PATH_ENV, str(db))

    with TestClient(app, base_url="http://127.0.0.1"):
        pass

    with open_database(db) as conn:
        assert status(conn, article_id) is ArticleStatus.NEW


def test_unknown_analyzer_fails_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(DB_PATH_ENV, str(tmp_path / "api.db"))
    monkeypatch.setenv("AI_RADAR_ANALYZER", "gpt")

    with pytest.raises(ValueError, match="Unknown analyzer"):
        with TestClient(app, base_url="http://127.0.0.1"):
            pass

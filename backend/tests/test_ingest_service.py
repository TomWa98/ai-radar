import sqlite3
from collections.abc import Iterator
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai_radar.articles.repository import ArticleRepository
from ai_radar.db import connect, open_database
from ai_radar.feeds.models import NewFeed
from ai_radar.feeds.repository import MAX_ERROR_LENGTH, FeedRepository
from ai_radar.ingest.__main__ import main, read_feed_list
from ai_radar.ingest.fetch import FetchedFeed, FetchError
from ai_radar.ingest.service import ingest_feeds, ingest_stored_feeds, redact_url

COLLECTED_AT = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)

FEED_A = b"""<rss version="2.0"><channel><title>Feed A</title>
  <item><title>One</title><link>https://example.com/1</link></item>
  <item><title>Two</title><link>https://example.com/2?utm_medium=rss</link></item>
</channel></rss>"""

# Shares article 2 with feed A under a different, equivalent URL.
FEED_B = b"""<feed xmlns="http://www.w3.org/2005/Atom"><title>Feed B</title>
  <entry><title>Two again</title><link href="https://EXAMPLE.com:443/2#top"/></entry>
  <entry><title>Three</title><link href="https://example.com/3"/></entry>
</feed>"""


class FakeFetcher:
    def __init__(self, responses: dict[str, bytes | FetchedFeed | Exception]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def __call__(self, url: str) -> FetchedFeed:
        self.calls.append(url)
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        if isinstance(response, bytes):
            return FetchedFeed(response, url)
        return response


@pytest.fixture
def repository(tmp_path: Path) -> Iterator[ArticleRepository]:
    with open_database(tmp_path / "radar.db") as conn:
        yield ArticleRepository(conn)


def test_ingests_rss_and_atom_without_duplicates(repository: ArticleRepository) -> None:
    fetch = FakeFetcher(
        {"https://a.example/rss": FEED_A, "https://b.example/atom": FEED_B}
    )

    results = ingest_feeds(fetch.responses, fetch, repository, lambda: COLLECTED_AT)

    assert [(r.new, r.duplicates, r.error) for r in results] == [
        (2, 0, None),
        (1, 1, None),
    ]
    stored = repository.get_by_url("https://example.com/2")
    assert stored is not None and stored.source == "Feed A"


def test_second_run_stores_nothing_new(repository: ArticleRepository) -> None:
    fetch = FakeFetcher({"https://a.example/rss": FEED_A})
    ingest_feeds(fetch.responses, fetch, repository, lambda: COLLECTED_AT)

    (result,) = ingest_feeds(fetch.responses, fetch, repository, lambda: COLLECTED_AT)
    assert (result.new, result.duplicates) == (0, 2)


def test_failing_feeds_do_not_stop_others(repository: ArticleRepository) -> None:
    fetch = FakeFetcher(
        {
            "https://down.example/rss": FetchError("Request failed: ConnectTimeout"),
            "https://broken.example/rss": b"<html>not a feed</html>",
            "https://bug.example/rss": RuntimeError("secret detail"),
            "https://a.example/rss": FEED_A,
        }
    )

    results = ingest_feeds(fetch.responses, fetch, repository, lambda: COLLECTED_AT)

    assert fetch.calls == list(fetch.responses)
    assert [r.ok for r in results] == [False, False, False, True]
    assert results[0].error == "Request failed: ConnectTimeout"
    assert results[1].error is not None and "Not a valid" in results[1].error
    assert results[2].error == "Unexpected RuntimeError"
    assert results[3].new == 2


def test_relative_links_use_final_url(repository: ArticleRepository) -> None:
    feed = b"""<rss version="2.0"><channel><title>Moved</title>
      <item><title>Rel</title><link>/posts/1</link></item>
    </channel></rss>"""
    fetch = FakeFetcher(
        {"https://old.example/rss": FetchedFeed(feed, "https://new.example/feeds/rss")}
    )

    (result,) = ingest_feeds(fetch.responses, fetch, repository, lambda: COLLECTED_AT)

    assert result.new == 1
    assert repository.get_by_url("https://new.example/posts/1") is not None
    assert repository.get_by_url("https://old.example/posts/1") is None


def test_redact_url() -> None:
    assert redact_url("https://user:pw@example.com/feed") == "https://example.com/feed"
    assert redact_url("https://example.com/feed") == "https://example.com/feed"


def test_read_feed_list(tmp_path: Path) -> None:
    path = tmp_path / "feeds.txt"
    path.write_text("# comment\n\nhttps://a.example/rss\n  https://b.example/atom  \n")
    assert read_feed_list(path) == ["https://a.example/rss", "https://b.example/atom"]


def test_cli_runs_ingestion(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    feeds = tmp_path / "feeds.txt"
    feeds.write_text("https://b.example/atom\n")
    fetch = FakeFetcher(
        {"https://a.example/rss": FEED_A, "https://b.example/atom": FEED_B}
    )
    db = tmp_path / "radar.db"

    code = main(
        ["--db", str(db), "--feeds-file", str(feeds), "https://a.example/rss"], fetch
    )

    assert code == 0
    assert fetch.calls == ["https://a.example/rss", "https://b.example/atom"]
    out = capsys.readouterr().out
    assert "https://a.example/rss: 2 new, 0 duplicates, 0 skipped" in out
    assert "https://b.example/atom: 1 new, 1 duplicates, 0 skipped" in out


def test_cli_reports_failures(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fetch = FakeFetcher({"https://down.example/rss": FetchError("HTTP status 503")})

    code = main(["--db", str(tmp_path / "radar.db"), "https://down.example/rss"], fetch)

    assert code == 1
    assert (
        "https://down.example/rss: failed: HTTP status 503" in capsys.readouterr().out
    )


def test_cli_rejects_missing_db_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fetch = FakeFetcher({"https://a.example/rss": FEED_A})
    db = tmp_path / "missing" / "radar.db"

    with pytest.raises(SystemExit) as exc:
        main(["--db", str(db), "https://a.example/rss"], fetch)

    assert exc.value.code == 2
    assert "database directory does not exist" in capsys.readouterr().err
    assert fetch.calls == []


def test_cli_rejects_empty_feeds_file(tmp_path: Path) -> None:
    feeds = tmp_path / "feeds.txt"
    feeds.write_text("# nothing here\n")

    with pytest.raises(SystemExit) as exc:
        main(
            ["--db", str(tmp_path / "radar.db"), "--feeds-file", str(feeds)],
            FakeFetcher({}),
        )
    assert exc.value.code == 2


# --- Stored feeds ---------------------------------------------------------


class StepClock:
    """Each call returns a time one minute after the previous one."""

    def __init__(self) -> None:
        self.now = COLLECTED_AT

    def __call__(self) -> datetime:
        current = self.now
        self.now += timedelta(minutes=1)
        return current


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with open_database(tmp_path / "radar.db") as connection:
        yield connection


def test_stored_feeds_are_ingested_with_status(conn: sqlite3.Connection) -> None:
    feeds = FeedRepository(conn)
    ok = feeds.add(NewFeed(url="https://a.example/rss"))
    down = feeds.add(NewFeed(url="https://down.example/rss"))
    off = feeds.add(NewFeed(url="https://off.example/rss", enabled=False))
    broken = feeds.add(NewFeed(url="https://broken.example/rss"))
    fetch = FakeFetcher(
        {
            "https://a.example/rss": FEED_A,
            "https://down.example/rss": FetchError("HTTP status 503"),
            "https://broken.example/rss": b"<html>not a feed</html>",
        }
    )
    articles = ArticleRepository(conn)

    results = ingest_stored_feeds(feeds, fetch, articles, StepClock())

    assert fetch.calls == [ok.url, down.url, broken.url]  # disabled feed skipped
    assert [r.ok for r in results] == [True, False, False]

    stored_ok = feeds.get_by_id(ok.id)
    assert stored_ok is not None
    assert stored_ok.last_fetched_at is not None
    assert stored_ok.last_success_at == stored_ok.last_fetched_at
    assert stored_ok.last_error is None

    stored_down = feeds.get_by_id(down.id)
    assert stored_down is not None
    assert stored_down.last_fetched_at is not None
    assert stored_down.last_success_at is None
    assert stored_down.last_error == "HTTP status 503"

    stored_broken = feeds.get_by_id(broken.id)
    assert stored_broken is not None and stored_broken.last_error is not None
    assert stored_broken.last_error.startswith("Not a valid RSS/Atom feed")
    assert "<html>" not in stored_broken.last_error  # no response content

    assert feeds.get_by_id(off.id) == off  # untouched

    article = articles.get_by_url("https://example.com/1")
    assert article is not None and article.feed_id == ok.id


def test_success_clears_previous_error(conn: sqlite3.Connection) -> None:
    feeds = FeedRepository(conn)
    feed = feeds.add(NewFeed(url="https://a.example/rss"))
    articles = ArticleRepository(conn)
    clock = StepClock()
    ingest_stored_feeds(
        feeds, FakeFetcher({feed.url: FetchError("HTTP status 500")}), articles, clock
    )

    ingest_stored_feeds(feeds, FakeFetcher({feed.url: FEED_A}), articles, clock)

    stored = feeds.get_by_id(feed.id)
    assert stored is not None
    assert stored.last_error is None
    assert stored.last_success_at == stored.last_fetched_at


def test_failed_fetch_keeps_last_success(conn: sqlite3.Connection) -> None:
    feeds = FeedRepository(conn)
    feed = feeds.add(NewFeed(url="https://a.example/rss"))
    articles = ArticleRepository(conn)
    clock = StepClock()
    ingest_stored_feeds(feeds, FakeFetcher({feed.url: FEED_A}), articles, clock)
    first = feeds.get_by_id(feed.id)
    assert first is not None

    ingest_stored_feeds(
        feeds, FakeFetcher({feed.url: FetchError("HTTP status 500")}), articles, clock
    )

    stored = feeds.get_by_id(feed.id)
    assert stored is not None and first.last_fetched_at is not None
    assert stored.last_success_at == first.last_success_at
    assert stored.last_fetched_at is not None
    assert stored.last_fetched_at > first.last_fetched_at
    assert stored.last_error == "HTTP status 500"


def test_unexpected_error_is_stored_without_detail(conn: sqlite3.Connection) -> None:
    feeds = FeedRepository(conn)
    feed = feeds.add(NewFeed(url="https://a.example/rss"))
    fetch = FakeFetcher({feed.url: RuntimeError("secret detail")})

    ingest_stored_feeds(feeds, fetch, ArticleRepository(conn), StepClock())

    stored = feeds.get_by_id(feed.id)
    assert stored is not None and stored.last_error == "Unexpected RuntimeError"


def test_status_write_failure_does_not_stop_other_feeds(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    feeds = FeedRepository(conn)
    first = feeds.add(NewFeed(url="https://a.example/rss"))
    second = feeds.add(NewFeed(url="https://b.example/atom"))
    fetch = FakeFetcher({first.url: FEED_A, second.url: FEED_B})

    def locked(self: FeedRepository, *args: object) -> None:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(FeedRepository, "record_fetch", locked)
    results = ingest_stored_feeds(feeds, fetch, ArticleRepository(conn), StepClock())

    assert fetch.calls == [first.url, second.url]
    assert [r.ok for r in results] == [True, True]


def test_long_error_is_truncated(conn: sqlite3.Connection) -> None:
    feeds = FeedRepository(conn)
    feed = feeds.add(NewFeed(url="https://a.example/rss"))
    fetch = FakeFetcher({feed.url: FetchError("x" * (MAX_ERROR_LENGTH + 100))})

    ingest_stored_feeds(feeds, fetch, ArticleRepository(conn), StepClock())

    stored = feeds.get_by_id(feed.id)
    assert stored is not None and stored.last_error == "x" * MAX_ERROR_LENGTH


def test_shared_article_keeps_first_feed(conn: sqlite3.Connection) -> None:
    feeds = FeedRepository(conn)
    feed_a = feeds.add(NewFeed(url="https://a.example/rss"))
    feed_b = feeds.add(NewFeed(url="https://b.example/atom"))
    fetch = FakeFetcher({feed_a.url: FEED_A, feed_b.url: FEED_B})
    articles = ArticleRepository(conn)

    ingest_stored_feeds(feeds, fetch, articles, StepClock())

    shared = articles.get_by_url("https://example.com/2")
    only_b = articles.get_by_url("https://example.com/3")
    assert shared is not None and shared.feed_id == feed_a.id
    assert only_b is not None and only_b.feed_id == feed_b.id


def test_url_ingestion_has_no_feed_link(repository: ArticleRepository) -> None:
    fetch = FakeFetcher({"https://a.example/rss": FEED_A})

    ingest_feeds(fetch.responses, fetch, repository, lambda: COLLECTED_AT)

    article = repository.get_by_url("https://example.com/1")
    assert article is not None and article.feed_id is None


def test_cli_without_urls_ingests_stored_feeds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "radar.db"
    with open_database(db) as conn:
        feeds = FeedRepository(conn)
        feed = feeds.add(NewFeed(url="https://a.example/rss"))
        feeds.add(NewFeed(url="https://off.example/rss", enabled=False))
    fetch = FakeFetcher({"https://a.example/rss": FEED_A})

    code = main(["--db", str(db)], fetch)

    assert code == 0
    assert fetch.calls == ["https://a.example/rss"]
    assert "https://a.example/rss: 2 new" in capsys.readouterr().out
    with closing(connect(db)) as conn:
        stored = FeedRepository(conn).get_by_id(feed.id)
    assert stored is not None and stored.last_success_at is not None


def test_cli_reports_stored_feed_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "radar.db"
    with open_database(db) as conn:
        FeedRepository(conn).add(NewFeed(url="https://down.example/rss"))
    fetch = FakeFetcher({"https://down.example/rss": FetchError("HTTP status 503")})

    assert main(["--db", str(db)], fetch) == 1
    assert "failed: HTTP status 503" in capsys.readouterr().out


def test_cli_without_stored_feeds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["--db", str(tmp_path / "radar.db")], FakeFetcher({}))

    assert code == 0
    assert "No enabled feeds stored." in capsys.readouterr().out


def test_cli_with_urls_does_not_touch_stored_feeds(tmp_path: Path) -> None:
    db = tmp_path / "radar.db"
    with open_database(db) as conn:
        stored = FeedRepository(conn).add(NewFeed(url="https://stored.example/rss"))
    fetch = FakeFetcher({"https://a.example/rss": FEED_A})

    assert main(["--db", str(db), "https://a.example/rss"], fetch) == 0

    assert fetch.calls == ["https://a.example/rss"]
    with closing(connect(db)) as conn:
        assert FeedRepository(conn).get_by_id(stored.id) == stored

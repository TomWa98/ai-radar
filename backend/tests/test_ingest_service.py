from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_radar.articles.repository import ArticleRepository
from ai_radar.db import open_database
from ai_radar.ingest.__main__ import main, read_feed_list
from ai_radar.ingest.fetch import FetchError
from ai_radar.ingest.service import ingest_feeds, redact_url

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
    def __init__(self, responses: dict[str, bytes | Exception]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
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


def test_cli_requires_feeds(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--db", str(tmp_path / "radar.db")], FakeFetcher({}))
    assert exc.value.code == 2

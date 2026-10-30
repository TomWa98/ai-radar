import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from pathlib import Path

import pytest

from ai_radar.articles.models import ArticleStatus, NewArticle
from ai_radar.articles.repository import ArticleRepository
from ai_radar.db import fetch_one, open_database, transaction

COLLECTED_AT = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


def make_article(
    url: str = "https://example.com/news/1", **overrides: object
) -> NewArticle:
    fields: dict[str, object] = {
        "source": "Example Feed",
        "url": url,
        "title": "Example headline",
        "content": "Original article text.",
        "published_at": datetime(2026, 10, 30, 9, 30, tzinfo=UTC),
        "collected_at": COLLECTED_AT,
    }
    fields.update(overrides)
    return NewArticle(**fields)


def count_articles(conn: sqlite3.Connection) -> int:
    row = fetch_one(conn, "SELECT COUNT(*) FROM articles")
    assert row is not None
    return row[0]


class _NoOffset(tzinfo):
    """A tzinfo that does not know its UTC offset."""

    def utcoffset(self, dt: datetime | None) -> None:
        return None


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def conn(db_path: Path) -> Iterator[sqlite3.Connection]:
    with open_database(db_path) as connection:
        yield connection


@pytest.fixture
def repo(conn: sqlite3.Connection) -> ArticleRepository:
    return ArticleRepository(conn)


def test_add_stores_all_fields(repo: ArticleRepository) -> None:
    stored = repo.add(make_article())

    assert stored is not None
    assert stored.id > 0
    assert stored.source == "Example Feed"
    assert stored.url == "https://example.com/news/1"
    assert stored.normalized_url == "https://example.com/news/1"
    assert stored.title == "Example headline"
    assert stored.content == "Original article text."
    assert stored.published_at == datetime(2026, 10, 30, 9, 30, tzinfo=UTC)
    assert stored.collected_at == COLLECTED_AT
    assert stored.status is ArticleStatus.NEW


def test_get_by_id_returns_stored_article(repo: ArticleRepository) -> None:
    stored = repo.add(make_article())
    assert stored is not None

    assert repo.get_by_id(stored.id) == stored


def test_get_by_id_unknown_returns_none(repo: ArticleRepository) -> None:
    assert repo.get_by_id(999) is None


def test_get_by_url_matches_normalized_variant(repo: ArticleRepository) -> None:
    stored = repo.add(make_article("https://example.com/news/1"))

    assert repo.get_by_url("https://EXAMPLE.com/news/1?utm_source=x#top") == stored
    assert repo.get_by_url("https://example.com/news/2") is None


def test_optional_fields_may_be_missing(repo: ArticleRepository) -> None:
    stored = repo.add(make_article(content=None, published_at=None))

    assert stored is not None
    assert stored.content is None
    assert stored.published_at is None


def test_timestamps_are_stored_in_utc_without_changing_the_instant(
    repo: ArticleRepository,
) -> None:
    cet = timezone(timedelta(hours=1))
    published_at = datetime(2026, 10, 30, 10, 30, tzinfo=cet)
    stored = repo.add(make_article(published_at=published_at))

    assert stored is not None
    assert stored.published_at == datetime(2026, 10, 30, 9, 30, tzinfo=UTC)
    assert stored.published_at.utcoffset() == timedelta(0)


def test_articles_persist_across_connections(db_path: Path) -> None:
    with open_database(db_path) as conn:
        stored = ArticleRepository(conn).add(make_article())
    assert stored is not None

    with open_database(db_path) as conn:
        assert ArticleRepository(conn).get_by_id(stored.id) == stored


@pytest.mark.parametrize(
    "duplicate_url",
    [
        "https://example.com/news/1",
        "HTTPS://Example.com/news/1",
        "https://example.com:443/news/1",
        "https://example.com/news/1#comments",
        "https://example.com/news/1?utm_source=rss&utm_medium=feed",
    ],
)
def test_duplicate_url_is_not_stored_twice(
    repo: ArticleRepository, conn: sqlite3.Connection, duplicate_url: str
) -> None:
    original = repo.add(make_article("https://example.com/news/1"))

    result = repo.add(make_article(duplicate_url, title="Different title"))

    assert result is None
    assert count_articles(conn) == 1
    assert original is not None
    assert repo.get_by_id(original.id) == original  # existing article unchanged


def test_distinct_urls_are_stored_separately(repo: ArticleRepository) -> None:
    urls = [
        "https://example.com/news/1",
        "http://example.com/news/1",
        "https://example.com/news/1/",
        "https://example.com/News/1",
        "https://example.com/news/1?page=2",
    ]

    stored = [repo.add(make_article(url)) for url in urls]

    assert all(article is not None for article in stored)
    assert len({article.id for article in stored if article is not None}) == len(urls)


@pytest.mark.parametrize("tz", [None, _NoOffset()])
@pytest.mark.parametrize("field", ["published_at", "collected_at"])
def test_datetime_without_utc_offset_is_rejected(field: str, tz: tzinfo | None) -> None:
    with pytest.raises(ValueError, match=field):
        make_article(**{field: datetime(2026, 10, 30, 12, 0, tzinfo=tz)})


def test_invalid_url_is_rejected_and_nothing_stored(
    repo: ArticleRepository, conn: sqlite3.Connection
) -> None:
    with pytest.raises(ValueError):
        repo.add(make_article("javascript:alert(1)"))

    assert count_articles(conn) == 0


def test_schema_rejects_unknown_status(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError), transaction(conn):
        conn.execute(
            """
            INSERT INTO articles
                (source, url, normalized_url, title, collected_at, status)
            VALUES ('s', 'https://e.com/a', 'https://e.com/a', 't', '2026-10-30',
                    'bogus')
            """
        )

    assert count_articles(conn) == 0


def test_failed_insert_is_rolled_back(
    repo: ArticleRepository, conn: sqlite3.Connection
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        repo.add(make_article(title=None))  # violates NOT NULL

    assert not conn.in_transaction
    assert count_articles(conn) == 0
    assert repo.add(make_article()) is not None  # connection still usable


def test_url_with_credentials_is_rejected_and_nothing_stored(
    repo: ArticleRepository, conn: sqlite3.Connection
) -> None:
    with pytest.raises(ValueError, match="credentials"):
        repo.add(make_article("https://user:secret@example.com/news/1"))

    assert count_articles(conn) == 0


def test_ids_of_deleted_articles_are_not_reused(
    repo: ArticleRepository, conn: sqlite3.Connection
) -> None:
    first = repo.add(make_article("https://example.com/news/1"))
    assert first is not None
    with transaction(conn):
        conn.execute("DELETE FROM articles WHERE id = ?", (first.id,))

    second = repo.add(make_article("https://example.com/news/2"))

    assert second is not None
    assert second.id > first.id

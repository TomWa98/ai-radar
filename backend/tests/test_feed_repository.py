import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai_radar.articles.models import NewArticle
from ai_radar.articles.repository import ArticleRepository
from ai_radar.db import fetch_one, open_database
from ai_radar.feeds.models import NewFeed
from ai_radar.feeds.repository import DuplicateFeedError, FeedRepository

CREATED_AT = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self) -> None:
        self.now = CREATED_AT

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with open_database(tmp_path / "test.db") as connection:
        yield connection


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def repo(conn: sqlite3.Connection, clock: FakeClock) -> FeedRepository:
    return FeedRepository(conn, clock)


def test_add_stores_all_fields_with_defaults(repo: FeedRepository) -> None:
    feed = repo.add(NewFeed(url="  https://Example.com/rss?utm_source=x  "))

    assert feed.url == "https://Example.com/rss?utm_source=x"
    assert feed.normalized_url == "https://example.com/rss"
    assert feed.name is None
    assert feed.enabled is True
    assert feed.fetch_full_text is False
    assert feed.created_at == feed.updated_at == CREATED_AT
    assert repo.get_by_id(feed.id) == feed


def test_add_stores_given_fields(repo: FeedRepository) -> None:
    feed = repo.add(
        NewFeed(
            url="https://example.com/atom",
            name="Example",
            enabled=False,
            fetch_full_text=True,
        )
    )

    assert (feed.name, feed.enabled, feed.fetch_full_text) == ("Example", False, True)
    assert repo.get_by_id(feed.id) == feed


def test_get_unknown_feed_returns_none(repo: FeedRepository) -> None:
    assert repo.get_by_id(42) is None


def test_list_all_returns_feeds_in_creation_order(repo: FeedRepository) -> None:
    assert repo.list_all() == []
    first = repo.add(NewFeed(url="https://b.example/rss"))
    second = repo.add(NewFeed(url="https://a.example/rss"))

    assert repo.list_all() == [first, second]


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/rss",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "https://user:secret@example.com/rss",
        "https:///rss",
        "example.com/rss",
        "",
    ],
)
def test_add_rejects_invalid_urls(repo: FeedRepository, url: str) -> None:
    with pytest.raises(ValueError):
        repo.add(NewFeed(url=url))
    assert repo.list_all() == []


def test_add_rejects_duplicate_without_changing_existing(
    repo: FeedRepository, clock: FakeClock
) -> None:
    existing = repo.add(NewFeed(url="https://example.com/rss", name="Original"))
    clock.now += timedelta(hours=1)

    with pytest.raises(DuplicateFeedError):
        repo.add(NewFeed(url="HTTPS://example.com:443/rss#top", name="Copy"))

    assert repo.list_all() == [existing]


def test_update_replaces_editable_fields(
    repo: FeedRepository, clock: FakeClock
) -> None:
    feed = repo.add(NewFeed(url="https://example.com/rss"))
    clock.now += timedelta(hours=1)

    updated = repo.update(
        feed.id,
        NewFeed(
            url="https://example.com/feed.xml",
            name="Renamed",
            enabled=False,
            fetch_full_text=True,
        ),
    )

    assert updated is not None
    assert updated.id == feed.id
    assert updated.normalized_url == "https://example.com/feed.xml"
    assert (updated.name, updated.enabled, updated.fetch_full_text) == (
        "Renamed",
        False,
        True,
    )
    assert updated.created_at == CREATED_AT
    assert updated.updated_at == clock.now
    assert repo.get_by_id(feed.id) == updated


def test_update_may_keep_own_url(repo: FeedRepository) -> None:
    feed = repo.add(NewFeed(url="https://example.com/rss"))

    updated = repo.update(feed.id, NewFeed(url="https://EXAMPLE.com/rss", name="n"))

    assert updated is not None
    assert (updated.normalized_url, updated.name) == (feed.normalized_url, "n")


def test_update_to_duplicate_url_changes_nothing(repo: FeedRepository) -> None:
    first = repo.add(NewFeed(url="https://a.example/rss"))
    second = repo.add(NewFeed(url="https://b.example/rss"))

    with pytest.raises(DuplicateFeedError):
        repo.update(second.id, NewFeed(url="https://A.example/rss", name="x"))

    assert repo.list_all() == [first, second]


def test_update_rejects_invalid_url(repo: FeedRepository) -> None:
    feed = repo.add(NewFeed(url="https://example.com/rss"))

    with pytest.raises(ValueError):
        repo.update(feed.id, NewFeed(url="ftp://example.com/rss"))

    assert repo.get_by_id(feed.id) == feed


def test_update_unknown_feed_returns_none(repo: FeedRepository) -> None:
    assert repo.update(42, NewFeed(url="https://example.com/rss")) is None
    assert repo.list_all() == []


def test_remove_deletes_feed(repo: FeedRepository) -> None:
    feed = repo.add(NewFeed(url="https://example.com/rss"))
    other = repo.add(NewFeed(url="https://other.example/rss"))

    assert repo.remove(feed.id) is True
    assert repo.get_by_id(feed.id) is None
    assert repo.list_all() == [other]
    assert repo.remove(feed.id) is False


def test_removed_feed_url_can_be_added_again(repo: FeedRepository) -> None:
    feed = repo.add(NewFeed(url="https://example.com/rss"))
    repo.remove(feed.id)

    again = repo.add(NewFeed(url="https://example.com/rss"))

    assert again.id != feed.id


def test_remove_keeps_articles(conn: sqlite3.Connection, repo: FeedRepository) -> None:
    feed = repo.add(NewFeed(url="https://example.com/rss"))
    articles = ArticleRepository(conn)
    article = articles.add(
        NewArticle(
            source="Example",
            url="https://example.com/posts/1",
            title="Post",
            content=None,
            published_at=None,
            collected_at=CREATED_AT,
        )
    )

    repo.remove(feed.id)

    assert article is not None
    assert articles.get_by_id(article.id) == article


def test_remove_clears_feed_link_of_articles(
    conn: sqlite3.Connection, repo: FeedRepository
) -> None:
    feed = repo.add(NewFeed(url="https://example.com/rss"))
    other = repo.add(NewFeed(url="https://other.example/rss"))
    articles = ArticleRepository(conn)

    def add_article(url: str, feed_id: int) -> int:
        article = articles.add(
            NewArticle(
                source="Example",
                url=url,
                title="Post",
                content=None,
                published_at=None,
                collected_at=CREATED_AT,
                feed_id=feed_id,
            )
        )
        assert article is not None and article.feed_id == feed_id
        return article.id

    removed_id = add_article("https://example.com/posts/1", feed.id)
    kept_id = add_article("https://other.example/posts/1", other.id)

    repo.remove(feed.id)

    removed_article = articles.get_by_id(removed_id)
    kept_article = articles.get_by_id(kept_id)
    assert removed_article is not None and removed_article.feed_id is None
    assert kept_article is not None and kept_article.feed_id == other.id


def test_new_feed_has_no_fetch_status(repo: FeedRepository) -> None:
    feed = repo.add(NewFeed(url="https://example.com/rss"))

    assert (feed.last_fetched_at, feed.last_success_at, feed.last_error) == (
        None,
        None,
        None,
    )


def test_list_enabled_skips_disabled_feeds(repo: FeedRepository) -> None:
    first = repo.add(NewFeed(url="https://a.example/rss"))
    repo.add(NewFeed(url="https://b.example/rss", enabled=False))
    third = repo.add(NewFeed(url="https://c.example/rss"))

    assert repo.list_enabled() == [first, third]


def test_schema_rejects_non_boolean_flags(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO feeds (url, normalized_url, enabled, created_at, updated_at)
            VALUES ('https://e.com/', 'https://e.com/', 2, 'x', 'x')
            """
        )
    row = fetch_one(conn, "SELECT COUNT(*) FROM feeds")
    assert row is not None and row[0] == 0

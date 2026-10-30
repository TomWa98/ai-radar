import sqlite3
import threading
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_radar.articles.models import NewArticle
from ai_radar.articles.repository import ArticleRepository
from ai_radar.db import (
    MIGRATIONS,
    SCHEMA_VERSION,
    Migration,
    connect,
    fetch_one,
    init_schema,
    open_database,
    transaction,
)

# Short lock timeout: a lock leak fails the test quickly instead of hanging.
FAST_TIMEOUT = 0.2


def make_article(url: str) -> NewArticle:
    return NewArticle(
        source="Example Feed",
        url=url,
        title="Example headline",
        content=None,
        published_at=None,
        collected_at=datetime(2026, 10, 30, 12, 0, tzinfo=UTC),
    )


def count_articles(conn: sqlite3.Connection) -> int:
    row = fetch_one(conn, "SELECT COUNT(*) FROM articles")
    assert row is not None
    return row[0]


def schema_version(path: Path) -> int:
    with closing(connect(path)) as conn:
        row = fetch_one(conn, "PRAGMA user_version")
    assert row is not None
    return row[0]


# Test-only migration on top of the real ones. CREATE TABLE without IF NOT EXISTS
# fails if it is ever applied twice.
TEST_MIGRATION: Migration = (
    "CREATE TABLE test_extra (id INTEGER PRIMARY KEY, url TEXT NOT NULL)",
    "ALTER TABLE articles ADD COLUMN test_extra_id INTEGER",
)
WITH_TEST = (*MIGRATIONS, TEST_MIGRATION)
TEST_VERSION = len(WITH_TEST)


def table_names(path: Path) -> set[str]:
    with closing(connect(path)) as conn:
        rows = conn.execute("SELECT name FROM sqlite_schema WHERE type = 'table'")
        return {row[0] for row in rows.fetchall()}


def migrate(path: Path, migrations: tuple[Migration, ...]) -> None:
    with closing(connect(path, timeout=5.0)) as conn:
        init_schema(conn, migrations)


def test_read_does_not_block_writer_on_other_connection(tmp_path: Path) -> None:
    path = tmp_path / "test.db"
    with (
        open_database(path, timeout=FAST_TIMEOUT) as reader_conn,
        open_database(path, timeout=FAST_TIMEOUT) as writer_conn,
    ):
        reader = ArticleRepository(reader_conn)
        assert reader.get_by_id(1) is None
        assert reader.get_by_url("https://example.com/a") is None
        assert not reader_conn.in_transaction

        stored = ArticleRepository(writer_conn).add(
            make_article("https://example.com/a")
        )

        assert stored is not None


def test_new_commits_are_visible_to_other_connection(tmp_path: Path) -> None:
    path = tmp_path / "test.db"
    with (
        open_database(path, timeout=FAST_TIMEOUT) as reader_conn,
        open_database(path, timeout=FAST_TIMEOUT) as writer_conn,
    ):
        reader = ArticleRepository(reader_conn)
        writer = ArticleRepository(writer_conn)
        assert reader.get_by_url("https://example.com/a") is None

        stored = writer.add(make_article("https://example.com/a"))

        assert reader.get_by_url("https://example.com/a") == stored
        assert stored is not None
        assert reader.get_by_id(stored.id) == stored


def test_concurrent_schema_initialization(tmp_path: Path) -> None:
    path = tmp_path / "test.db"
    workers = 4
    barrier = threading.Barrier(workers)
    errors: list[BaseException] = []

    def start() -> None:
        try:
            barrier.wait()
            with open_database(path):
                pass
        except BaseException as exc:  # collected and asserted below
            errors.append(exc)

    threads = [threading.Thread(target=start) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert schema_version(path) == SCHEMA_VERSION


def test_init_waits_for_concurrent_writer_instead_of_failing(tmp_path: Path) -> None:
    path = tmp_path / "test.db"
    results: list[object] = []

    def start() -> None:
        try:
            with open_database(path, timeout=5.0) as conn:
                results.append(count_articles(conn))
        except BaseException as exc:  # collected and asserted below
            results.append(exc)

    with closing(connect(path)) as blocker:
        blocker.execute("BEGIN IMMEDIATE")  # another process holds the write lock
        thread = threading.Thread(target=start)
        thread.start()
        thread.join(timeout=0.3)
        assert thread.is_alive()  # waiting for the lock, not failing
        blocker.execute("ROLLBACK")
    thread.join()

    assert results == [0]
    assert schema_version(path) == SCHEMA_VERSION


def test_unknown_schema_version_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "test.db"
    with closing(connect(path)) as conn:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1:d}")

    with pytest.raises(RuntimeError, match="Unsupported database schema version"):
        with open_database(path):
            pass

    assert schema_version(path) == SCHEMA_VERSION + 1  # left untouched


def test_reopening_database_keeps_schema_and_data(tmp_path: Path) -> None:
    path = tmp_path / "test.db"
    with open_database(path) as conn:
        ArticleRepository(conn).add(make_article("https://example.com/a"))

    with open_database(path) as conn:
        assert count_articles(conn) == 1

    assert schema_version(path) == SCHEMA_VERSION


def test_transaction_rolls_back_on_error(tmp_path: Path) -> None:
    with open_database(tmp_path / "test.db") as conn:
        with pytest.raises(RuntimeError), transaction(conn):
            conn.execute(
                """
                INSERT INTO articles (source, url, normalized_url, title, collected_at)
                VALUES ('s', 'https://e.com/a', 'https://e.com/a', 't', 'x')
                """
            )
            raise RuntimeError("boom")

        assert not conn.in_transaction
        assert count_articles(conn) == 0


def test_migrations_are_numbered_by_position() -> None:
    assert SCHEMA_VERSION == len(MIGRATIONS) >= 1


def test_empty_database_is_migrated_to_latest(tmp_path: Path) -> None:
    path = tmp_path / "test.db"

    migrate(path, WITH_TEST)

    assert schema_version(path) == TEST_VERSION
    assert {"articles", "feeds", "test_extra"} <= table_names(path)


def test_populated_v1_database_is_migrated_without_losing_articles(
    tmp_path: Path,
) -> None:
    path = tmp_path / "test.db"
    migrate(path, MIGRATIONS[:1])
    assert schema_version(path) == 1
    with closing(connect(path)) as conn:
        # Raw v1 rows: the repository always targets the latest schema.
        for url in ("https://example.com/a", "https://example.com/b"):
            conn.execute(
                """
                INSERT INTO articles
                    (source, url, normalized_url, title, content, collected_at)
                VALUES ('Example Feed', ?, ?, 'Example headline', 'Text',
                        '2026-10-30T12:00:00+00:00')
                """,
                (url, url),
            )

    migrate(path, WITH_TEST)

    assert schema_version(path) == TEST_VERSION
    assert "feeds" in table_names(path)
    with closing(connect(path)) as conn:
        repository = ArticleRepository(conn)
        for article_id, url in (
            (1, "https://example.com/a"),
            (2, "https://example.com/b"),
        ):
            article = repository.get_by_id(article_id)
            assert article is not None
            assert (article.url, article.title, article.content) == (
                url,
                "Example headline",
                "Text",
            )
            assert article.collected_at == datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
            assert article.feed_id is None
            assert (article.full_text, article.analysis_basis) == (None, None)
        row = fetch_one(conn, "SELECT test_extra_id FROM articles LIMIT 1")
        assert row is not None and row[0] is None


def test_failing_migration_keeps_previous_version(tmp_path: Path) -> None:
    path = tmp_path / "test.db"
    with open_database(path) as conn:
        ArticleRepository(conn).add(make_article("https://example.com/a"))
    broken: Migration = (
        "CREATE TABLE half_done (id INTEGER)",
        "ALTER TABLE no_such_table ADD COLUMN x INTEGER",
    )

    with closing(connect(path)) as conn:
        with pytest.raises(sqlite3.OperationalError):
            init_schema(conn, (*WITH_TEST, broken))
        assert not conn.in_transaction

    # The test migration committed; the broken one rolled back entirely.
    assert schema_version(path) == TEST_VERSION
    assert "half_done" not in table_names(path)
    with closing(connect(path)) as conn:
        assert count_articles(conn) == 1


def test_concurrent_migration_applies_each_migration_once(tmp_path: Path) -> None:
    path = tmp_path / "test.db"
    with open_database(path):
        pass
    workers = 4
    barrier = threading.Barrier(workers)
    errors: list[BaseException] = []

    def start() -> None:
        try:
            barrier.wait()
            migrate(path, WITH_TEST)
        except BaseException as exc:  # collected and asserted below
            errors.append(exc)

    threads = [threading.Thread(target=start) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert schema_version(path) == TEST_VERSION

"""SQLite connection handling, transactions, and schema migrations.

Transaction strategy:

* Connections run with ``autocommit=True``, i.e. SQLite's native mode: every
  statement outside an explicit transaction is its own short transaction. Reads
  therefore never leave a lock or a stale snapshot behind.
* Every write goes through :func:`transaction`, which starts with
  ``BEGIN IMMEDIATE``. The write lock is taken up front, so concurrent writers
  wait (up to ``timeout`` seconds) instead of deadlocking on a lock upgrade.

``with conn:`` must not be used for this: with ``autocommit=True`` it does
nothing.

Schema migrations (decision D1 in ``docs/architecture.md``):

* :data:`MIGRATIONS` is an ordered list; migration ``n`` (1-based) brings the
  database from ``PRAGMA user_version`` ``n - 1`` to ``n``.
* Migrations only add tables, columns, and indexes. Never edit or reorder a
  released migration; append a new one instead.
"""

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

Migration = tuple[str, ...]  # SQL statements, run in one transaction

_V1_ARTICLES = """
CREATE TABLE articles (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source         TEXT NOT NULL,
    url            TEXT NOT NULL,
    normalized_url TEXT NOT NULL UNIQUE,
    title          TEXT NOT NULL,
    content        TEXT,
    published_at   TEXT,
    collected_at   TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'new'
                   CHECK (status IN ('new', 'processing', 'analyzed', 'failed'))
)
"""

# Feeds are not linked to articles, so removing a feed never removes articles.
_V2_FEEDS = """
CREATE TABLE feeds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT NOT NULL,
    normalized_url  TEXT NOT NULL UNIQUE,
    name            TEXT,
    enabled         INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    fetch_full_text INTEGER NOT NULL DEFAULT 0 CHECK (fetch_full_text IN (0, 1)),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
)
"""

# Per-feed fetch status, and the feed each new article came from. Articles
# collected before this migration keep feed_id NULL. There is no foreign key
# (not enforced without PRAGMA foreign_keys); FeedRepository.remove clears it.
_V3_FEED_STATUS: Migration = (
    "ALTER TABLE feeds ADD COLUMN last_fetched_at TEXT",
    "ALTER TABLE feeds ADD COLUMN last_success_at TEXT",
    "ALTER TABLE feeds ADD COLUMN last_error TEXT",
    "ALTER TABLE articles ADD COLUMN feed_id INTEGER",
    "CREATE INDEX articles_feed_id ON articles (feed_id)",
)

# Full text extracted from the article page (D3) and which text an analysis
# should use. The feed excerpt stays in ``content``. Articles collected before
# this migration keep analysis_basis NULL (they only have the excerpt).
_V4_FULL_TEXT: Migration = (
    "ALTER TABLE articles ADD COLUMN full_text TEXT",
    """
    ALTER TABLE articles ADD COLUMN analysis_basis TEXT
        CHECK (analysis_basis IN ('full_text', 'excerpt'))
    """,
)

# Analyses (D4-D6): categories, scores, topics, basis, and usage are
# language-independent; summaries and reasons are stored once per language.
# An article may have several analyses (retries); articles stay unchanged.
_V5_ANALYSES: Migration = (
    """
    CREATE TABLE analyses (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id           INTEGER NOT NULL,
        primary_category     TEXT NOT NULL CHECK (primary_category IN
                             ('Releases', 'Features', 'Security', 'Use Cases',
                              'Other')),
        secondary_categories TEXT NOT NULL DEFAULT '[]',  -- JSON array
        importance           INTEGER NOT NULL CHECK (importance BETWEEN 1 AND 5),
        relevance            INTEGER NOT NULL CHECK (relevance BETWEEN 1 AND 5),
        topics               TEXT NOT NULL DEFAULT '[]',  -- JSON array
        analysis_basis       TEXT NOT NULL
                             CHECK (analysis_basis IN ('full_text', 'excerpt')),
        model                TEXT NOT NULL,
        input_tokens         INTEGER NOT NULL CHECK (input_tokens >= 0),
        output_tokens        INTEGER NOT NULL CHECK (output_tokens >= 0),
        estimated_cost       REAL NOT NULL CHECK (estimated_cost >= 0),
        analyzed_at          TEXT NOT NULL
    )
    """,
    "CREATE INDEX analyses_article_id ON analyses (article_id)",
    """
    CREATE TABLE analysis_texts (
        analysis_id      INTEGER NOT NULL,
        language         TEXT NOT NULL CHECK (language IN ('de', 'en')),
        summary          TEXT NOT NULL,
        relevance_reason TEXT NOT NULL,
        PRIMARY KEY (analysis_id, language)
    )
    """,
)

# Analysis bookkeeping per article (FR-13, FR-33): finished attempts, the
# safe message of the last failure, and when the last attempt was claimed.
_V6_ANALYSIS_STATUS: Migration = (
    "ALTER TABLE articles ADD COLUMN analysis_attempts INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE articles ADD COLUMN analysis_error TEXT",
    "ALTER TABLE articles ADD COLUMN analysis_attempted_at TEXT",
    "CREATE INDEX articles_status ON articles (status)",
)

# One row per paid LLM API call that returned usage (D5), including calls whose
# output was rejected; the monthly budget is checked against these rows.
_V7_LLM_CALLS: Migration = (
    """
    CREATE TABLE llm_calls (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        called_at      TEXT NOT NULL,
        model          TEXT NOT NULL,
        input_tokens   INTEGER NOT NULL CHECK (input_tokens >= 0),
        output_tokens  INTEGER NOT NULL CHECK (output_tokens >= 0),
        estimated_cost REAL NOT NULL CHECK (estimated_cost >= 0)
    )
    """,
    "CREATE INDEX llm_calls_called_at ON llm_calls (called_at)",
)

# Manual interests (FR-14). topic_key is the normalized, case-folded topic, so
# "LLM" and "llm" are the same interest. Only the user changes these rows.
_V8_INTERESTS = """
CREATE TABLE interests (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    topic      TEXT NOT NULL,
    topic_key  TEXT NOT NULL UNIQUE,
    weight     TEXT NOT NULL CHECK (weight IN ('low', 'medium', 'high')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

# Relevance feedback (FR-15): at most one rating per article. Feedback never
# changes stored analyses; preferences are derived from it separately (D6).
_V9_FEEDBACK = """
CREATE TABLE article_feedback (
    article_id INTEGER PRIMARY KEY,
    rating     TEXT NOT NULL CHECK (rating IN ('relevant', 'irrelevant')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

# Resets of the learned preferences (D6, FR-18). Learned preferences are
# derived from feedback given after the latest reset, so a reset keeps all
# stored feedback and the manual interests.
_V10_PREFERENCE_RESETS = """
CREATE TABLE preference_resets (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    reset_at TEXT NOT NULL
)
"""

# Full-text search over title, feed excerpt, and extracted text (D7, FR-20).
# External-content FTS5 index: filled once for existing articles, then kept
# current by triggers. Status updates do not touch the index.
_V11_ARTICLE_SEARCH: Migration = (
    """
    CREATE VIRTUAL TABLE articles_fts USING fts5(
        title, content, full_text,
        content = 'articles', content_rowid = 'id',
        tokenize = 'unicode61 remove_diacritics 2'
    )
    """,
    "INSERT INTO articles_fts (articles_fts) VALUES ('rebuild')",
    """
    CREATE TRIGGER articles_fts_insert AFTER INSERT ON articles BEGIN
        INSERT INTO articles_fts (rowid, title, content, full_text)
        VALUES (new.id, new.title, new.content, new.full_text);
    END
    """,
    """
    CREATE TRIGGER articles_fts_delete AFTER DELETE ON articles BEGIN
        INSERT INTO articles_fts (articles_fts, rowid, title, content, full_text)
        VALUES ('delete', old.id, old.title, old.content, old.full_text);
    END
    """,
    """
    CREATE TRIGGER articles_fts_update
    AFTER UPDATE OF title, content, full_text ON articles BEGIN
        INSERT INTO articles_fts (articles_fts, rowid, title, content, full_text)
        VALUES ('delete', old.id, old.title, old.content, old.full_text);
        INSERT INTO articles_fts (rowid, title, content, full_text)
        VALUES (new.id, new.title, new.content, new.full_text);
    END
    """,
)

MIGRATIONS: tuple[Migration, ...] = (
    (_V1_ARTICLES,),
    (_V2_FEEDS,),
    _V3_FEED_STATUS,
    _V4_FULL_TEXT,
    _V5_ANALYSES,
    _V6_ANALYSIS_STATUS,
    _V7_LLM_CALLS,
    (_V8_INTERESTS,),
    (_V9_FEEDBACK,),
    (_V10_PREFERENCE_RESETS,),
    _V11_ARTICLE_SEARCH,
)

SCHEMA_VERSION = len(MIGRATIONS)

DEFAULT_TIMEOUT = 5.0


def connect(path: Path, timeout: float = DEFAULT_TIMEOUT) -> sqlite3.Connection:
    """Open a connection; ``timeout`` is how long to wait for a locked database."""
    conn = sqlite3.connect(path, timeout=timeout, autocommit=True)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[None]:
    """Run a block as one write transaction: commit on success, roll back on error.

    Transactions cannot be nested; SQLite rejects a second ``BEGIN``.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
        conn.execute("COMMIT")
    except BaseException:
        # SQLite may already have rolled back on its own (e.g. disk full).
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def fetch_one(
    conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()
) -> sqlite3.Row | None:
    """Run a query and return its first row, releasing the statement immediately."""
    with closing(conn.execute(sql, params)) as cursor:
        return cursor.fetchone()


_FTS5_PROBE = "CREATE VIRTUAL TABLE temp.fts5_probe USING fts5(x)"


def require_fts5(conn: sqlite3.Connection) -> None:
    """Raise ``RuntimeError`` if this SQLite build lacks FTS5 (needed, D7)."""
    try:
        conn.execute(_FTS5_PROBE)
    except sqlite3.OperationalError as exc:
        raise RuntimeError(
            "SQLite FTS5 is not available, but AI Radar needs it for full-text "
            "search (D7). Use a Python build whose SQLite includes FTS5."
        ) from exc
    conn.execute("DROP TABLE temp.fts5_probe")


def init_schema(
    conn: sqlite3.Connection, migrations: Sequence[Migration] = MIGRATIONS
) -> None:
    """Apply all pending migrations; leave an up-to-date database untouched.

    Each migration runs in its own write transaction together with its version
    update, so a failing migration leaves the previous version intact. The
    version is read inside that transaction, so two processes starting at the
    same time cannot both apply the same migration.

    Fails with a clear ``RuntimeError`` if SQLite lacks FTS5.
    """
    require_fts5(conn)
    latest = len(migrations)
    while True:
        with transaction(conn):
            row = fetch_one(conn, "PRAGMA user_version")
            assert row is not None
            version = row[0]
            if version == latest:
                return
            if not 0 <= version < latest:
                raise RuntimeError(f"Unsupported database schema version: {version}")
            for statement in migrations[version]:
                conn.execute(statement)
            # PRAGMA values cannot be bound as parameters; this is an integer.
            conn.execute(f"PRAGMA user_version = {version + 1:d}")


@contextmanager
def open_database(
    path: Path, timeout: float = DEFAULT_TIMEOUT
) -> Iterator[sqlite3.Connection]:
    """Open the database, ensure the schema exists, and always close it afterwards."""
    conn = connect(path, timeout)
    try:
        init_schema(conn)
        yield conn
    finally:
        conn.close()

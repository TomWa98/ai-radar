"""SQLite connection handling, transactions, and schema setup.

Transaction strategy:

* Connections run with ``autocommit=True``, i.e. SQLite's native mode: every
  statement outside an explicit transaction is its own short transaction. Reads
  therefore never leave a lock or a stale snapshot behind.
* Every write goes through :func:`transaction`, which starts with
  ``BEGIN IMMEDIATE``. The write lock is taken up front, so concurrent writers
  wait (up to ``timeout`` seconds) instead of deadlocking on a lock upgrade.

``with conn:`` must not be used for this: with ``autocommit=True`` it does
nothing.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

# PRAGMA values cannot be bound as parameters; the version is a constant integer.
_SET_SCHEMA_VERSION = f"PRAGMA user_version = {SCHEMA_VERSION:d}"

_SCHEMA = """
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


def init_schema(conn: sqlite3.Connection) -> None:
    """Create the schema in an empty database; leave an up-to-date one untouched.

    The version check runs inside the write transaction, so two processes
    starting at the same time cannot both decide to create the schema.
    """
    with transaction(conn):
        row = fetch_one(conn, "PRAGMA user_version")
        assert row is not None
        version = row[0]
        if version == SCHEMA_VERSION:
            return
        if version != 0:
            raise RuntimeError(f"Unsupported database schema version: {version}")
        conn.execute(_SCHEMA)
        conn.execute(_SET_SCHEMA_VERSION)


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

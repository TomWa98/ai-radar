import sqlite3
from collections.abc import Iterator
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ai_radar import db as db_module
from ai_radar.analysis.models import AnalysisResult, LocalizedText, Usage
from ai_radar.analysis.repository import AnalysisRepository
from ai_radar.articles.listing import ArticleQuery, list_articles, to_fts_query
from ai_radar.articles.models import AnalysisBasis, NewArticle
from ai_radar.articles.repository import ArticleRepository
from ai_radar.db import MIGRATIONS, connect, init_schema, open_database
from ai_radar.main import DB_PATH_ENV, app

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def add(
    conn: sqlite3.Connection,
    slug: str,
    title: str,
    content: str | None = None,
    days: int = 0,
) -> int:
    article = ArticleRepository(conn).add(
        NewArticle(
            source="Feed",
            url=f"https://example.com/{slug}",
            title=title,
            content=content,
            published_at=T0 + timedelta(days=days),
            collected_at=T0,
        )
    )
    assert article is not None
    return article.id


def search(conn: sqlite3.Connection, text: str, **filters: Any) -> list[str]:
    page = list_articles(conn, ArticleQuery(search=text, **filters))
    return [item.title for item in page.items]


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with open_database(tmp_path / "test.db") as connection:
        yield connection


# --- Query conversion -----------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("llm", '"llm"'),
        ("open  source", '"open" "source"'),
        ('say "hi"', '"say" """hi"""'),
        ("NOT OR AND", '"NOT" "OR" "AND"'),
        ("title:x", '"title:x"'),
        ("a\x00b", '"a" "b"'),
        ("\x00\x07", None),
    ],
)
def test_to_fts_query(text: str | None, expected: str | None) -> None:
    assert to_fts_query(text) == expected


def test_to_fts_query_limits() -> None:
    with pytest.raises(ValueError, match="terms"):
        to_fts_query(" ".join(["x"] * 21))
    with pytest.raises(ValueError, match="characters"):
        to_fts_query("x" * 201)


# --- Index and triggers ---------------------------------------------------------


def test_search_title_excerpt_and_full_text(conn: sqlite3.Connection) -> None:
    add(conn, "a", "Neue Regulierung für KI", "Brüssel beschließt Regeln")
    b = add(conn, "b", "Model release", "Faster inference")
    add(conn, "c", "Unrelated", None)
    ArticleRepository(conn).set_full_text(b, "The model supports agents and tools.")

    assert search(conn, "regulierung") == ["Neue Regulierung für KI"]
    assert search(conn, "bruessel") == []
    assert search(conn, "brussel") == ["Neue Regulierung für KI"]  # diacritics
    assert search(conn, "inference") == ["Model release"]
    assert search(conn, "agents") == ["Model release"]  # extracted text
    assert search(conn, "model agents") == ["Model release"]  # all terms
    assert search(conn, "model regulierung") == []


def test_index_follows_updates(conn: sqlite3.Connection) -> None:
    article_id = add(conn, "a", "Original title", "old words")
    articles = ArticleRepository(conn)

    articles.set_full_text(article_id, "fresh extracted words")
    articles.claim_for_analysis(10, 3, T0, T0)  # status change only
    conn.execute(
        "UPDATE articles SET title = 'Renamed title' WHERE id = ?", (article_id,)
    )

    assert search(conn, "extracted") == ["Renamed title"]
    assert search(conn, "renamed") == ["Renamed title"]
    assert search(conn, "original") == []
    assert search(conn, "old") == ["Renamed title"]  # excerpt unchanged


def test_index_follows_deletes(conn: sqlite3.Connection) -> None:
    article_id = add(conn, "a", "Doomed article")
    conn.execute("DELETE FROM articles WHERE id = ?", (article_id,))
    assert search(conn, "doomed") == []
    integrity = conn.execute(
        "INSERT INTO articles_fts (articles_fts) VALUES ('integrity-check')"
    )
    assert integrity is not None  # raises if the index is inconsistent


def test_migration_indexes_existing_articles(tmp_path: Path) -> None:
    path = tmp_path / "test.db"
    with closing(connect(path)) as conn:
        init_schema(conn, MIGRATIONS[:-1])
        conn.execute(
            """
            INSERT INTO articles (source, url, normalized_url, title, content,
                                  collected_at)
            VALUES ('s', 'https://e.com/a', 'https://e.com/a',
                    'Historic quantum article', 'old excerpt',
                    '2020-01-01T00:00:00+00:00')
            """
        )

    with open_database(path) as conn:
        assert search(conn, "quantum") == ["Historic quantum article"]
        conn.execute(
            "INSERT INTO articles_fts (articles_fts) VALUES ('integrity-check')"
        )


@pytest.mark.parametrize(
    "text",
    [
        '"',
        '""',
        "*",
        "a*",
        "^start",
        "NEAR(a b)",
        "a OR",
        "AND",
        "(",
        "title:x",
        "-x",
        "col:",
        "'; DROP TABLE articles; --",
        "\x00",
        "üñí©ødé",
    ],
)
def test_special_characters_never_fail(conn: sqlite3.Connection, text: str) -> None:
    add(conn, "a", "Plain article")
    search(conn, text)  # no exception
    assert search(conn, "plain") == ["Plain article"]


def test_operators_are_literal_text(conn: sqlite3.Connection) -> None:
    add(conn, "a", "Alpha news")
    add(conn, "b", "Beta news")
    assert search(conn, "alpha OR beta") == []  # "or" must also appear


# --- Combined with filters ------------------------------------------------------


def test_search_combines_with_filters(conn: sqlite3.Connection) -> None:
    secure = add(conn, "a", "Security patch for agents", days=2)
    add(conn, "b", "Agents framework release", days=1)
    text = LocalizedText(de="x", en="x")
    AnalysisRepository(conn).add(
        secure,
        AnalysisResult(
            summary=text,
            primary_category="Security",
            importance=3,
            relevance=5,
            relevance_reason=text,
            basis=AnalysisBasis.EXCERPT,
            usage=Usage(model="m", input_tokens=0, output_tokens=0, estimated_cost=0),
        ),
        T0,
    )

    assert search(conn, "agents") == [
        "Security patch for agents",
        "Agents framework release",
    ]
    assert search(conn, "agents", min_relevance=4) == ["Security patch for agents"]
    page = list_articles(conn, ArticleQuery(search="agents", limit=1))
    assert page.total == 2 and len(page.items) == 1


# --- FTS5 availability ----------------------------------------------------------


def test_missing_fts5_is_a_clear_startup_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        db_module, "_FTS5_PROBE", "CREATE VIRTUAL TABLE temp.p USING no_such_module(x)"
    )
    monkeypatch.setenv(DB_PATH_ENV, str(tmp_path / "api.db"))

    with pytest.raises(RuntimeError, match="FTS5 is not available"):
        with TestClient(app, base_url="http://127.0.0.1"):
            pass


# --- API ------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    path = tmp_path / "api.db"
    monkeypatch.setenv(DB_PATH_ENV, str(path))
    with open_database(path) as conn:
        add(conn, "a", "Open source model", "weights released", days=1)
        add(conn, "b", "Closed model", None, days=2)
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client


def test_api_search(client: TestClient) -> None:
    def titles(**params: Any) -> list[str]:
        response = client.get("/api/articles", params=params)
        assert response.status_code == 200, response.text
        return [item["title"] for item in response.json()["items"]]

    assert titles(q="model") == ["Closed model", "Open source model"]
    assert titles(q="weights") == ["Open source model"]
    assert titles(q="  ") == ["Closed model", "Open source model"]  # blank: all
    assert titles(q='"*(') == []


@pytest.mark.parametrize("q", ["x" * 201, " ".join(["x"] * 21)])
def test_api_rejects_oversized_search(client: TestClient, q: str) -> None:
    assert client.get("/api/articles", params={"q": q}).status_code == 422

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ai_radar.analysis.analyzer import FakeAnalyzer
from ai_radar.analysis.models import AnalysisInput
from ai_radar.analysis.repository import AnalysisRepository
from ai_radar.articles.models import AnalysisBasis, NewArticle
from ai_radar.articles.repository import ArticleRepository
from ai_radar.db import fetch_one, open_database
from ai_radar.feedback.repository import FeedbackRepository, Rating
from ai_radar.main import DB_PATH_ENV, app

T0 = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


class StepClock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        current = self.now
        self.now += timedelta(minutes=1)
        return current


def add_article(conn: sqlite3.Connection, slug: str = "a") -> int:
    article = ArticleRepository(conn).add(
        NewArticle(
            source="s",
            url=f"https://example.com/{slug}",
            title="Title",
            content="Excerpt",
            published_at=None,
            collected_at=T0,
        )
    )
    assert article is not None
    return article.id


# --- Repository -------------------------------------------------------------


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with open_database(tmp_path / "test.db") as connection:
        yield connection


def test_set_change_and_remove(conn: sqlite3.Connection) -> None:
    article_id = add_article(conn)
    repo = FeedbackRepository(conn, StepClock())

    first = repo.set(article_id, Rating.RELEVANT)
    changed = repo.set(article_id, Rating.IRRELEVANT)

    assert first is not None and changed is not None
    assert changed.rating is Rating.IRRELEVANT
    assert changed.created_at == first.created_at  # same feedback, updated
    assert changed.updated_at > first.updated_at
    assert repo.get(article_id) == changed
    row = fetch_one(conn, "SELECT COUNT(*) FROM article_feedback")
    assert row is not None and row[0] == 1  # at most one per article

    assert repo.remove(article_id) is True
    assert repo.get(article_id) is None
    assert repo.remove(article_id) is True  # idempotent for a known article


def test_unknown_article(conn: sqlite3.Connection) -> None:
    repo = FeedbackRepository(conn)
    assert repo.set(42, Rating.RELEVANT) is None
    assert repo.remove(42) is False
    row = fetch_one(conn, "SELECT COUNT(*) FROM article_feedback")
    assert row is not None and row[0] == 0


def test_schema_rejects_unknown_rating(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO article_feedback VALUES (1, 'meh', 'now', 'now')")


def test_feedback_does_not_change_analyses(conn: sqlite3.Connection) -> None:
    article_id = add_article(conn)
    analyses = AnalysisRepository(conn)
    result = FakeAnalyzer().analyze(
        AnalysisInput(title="Title", text="Excerpt", basis=AnalysisBasis.EXCERPT)
    )
    stored = analyses.add(article_id, result, T0)
    article_before = ArticleRepository(conn).get_by_id(article_id)

    repo = FeedbackRepository(conn)
    repo.set(article_id, Rating.IRRELEVANT)
    repo.remove(article_id)

    assert analyses.latest_for_article(article_id) == stored
    assert ArticleRepository(conn).get_by_id(article_id) == article_before


# --- API ----------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "api.db"
    monkeypatch.setenv(DB_PATH_ENV, str(path))
    return path


@pytest.fixture
def client(db_path: Path) -> Iterator[TestClient]:
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client


@pytest.fixture
def article_id(client: TestClient, db_path: Path) -> int:
    with open_database(db_path) as conn:
        return add_article(conn)


def stored_rating(db_path: Path, article_id: int) -> Rating | None:
    with open_database(db_path) as conn:
        feedback = FeedbackRepository(conn).get(article_id)
    return None if feedback is None else feedback.rating


def test_put_sets_and_changes_feedback(
    client: TestClient, article_id: int, db_path: Path
) -> None:
    response = client.put(
        f"/api/articles/{article_id}/feedback", json={"rating": "relevant"}
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["article_id"], body["rating"]) == (article_id, "relevant")
    assert set(body) == {"article_id", "rating", "created_at", "updated_at"}

    changed = client.put(
        f"/api/articles/{article_id}/feedback", json={"rating": "irrelevant"}
    )
    assert changed.status_code == 200
    assert changed.json()["created_at"] == body["created_at"]
    assert stored_rating(db_path, article_id) is Rating.IRRELEVANT


def test_delete_removes_feedback(
    client: TestClient, article_id: int, db_path: Path
) -> None:
    client.put(f"/api/articles/{article_id}/feedback", json={"rating": "relevant"})

    response = client.delete(f"/api/articles/{article_id}/feedback")

    assert response.status_code == 204 and response.content == b""
    assert stored_rating(db_path, article_id) is None
    assert client.delete(f"/api/articles/{article_id}/feedback").status_code == 204


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
def test_unknown_article_returns_404(client: TestClient, method: str) -> None:
    kwargs: dict[str, Any] = {"json": {"rating": "relevant"}} if method == "PUT" else {}

    response = client.request(method, "/api/articles/999/feedback", **kwargs)

    assert response.status_code == 404
    assert response.json() == {"detail": "Article not found"}


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"rating": None},
        {"rating": "maybe"},
        {"rating": "Relevant"},
        {"rating": 1},
        {"rating": "relevant", "comment": "x"},
    ],
)
def test_invalid_rating_returns_422(
    client: TestClient, article_id: int, db_path: Path, body: dict[str, Any]
) -> None:
    response = client.put(f"/api/articles/{article_id}/feedback", json=body)
    assert response.status_code == 422
    assert stored_rating(db_path, article_id) is None


@pytest.mark.parametrize("article_ref", ["0", "-1", "abc", str(2**63)])
def test_invalid_article_id_returns_422(client: TestClient, article_ref: str) -> None:
    response = client.put(
        f"/api/articles/{article_ref}/feedback", json={"rating": "relevant"}
    )
    assert response.status_code == 422


def test_foreign_host_is_rejected(client: TestClient, article_id: int) -> None:
    response = client.put(
        f"/api/articles/{article_id}/feedback",
        json={"rating": "relevant"},
        headers={"Host": "attacker.example"},
    )
    assert response.status_code == 400

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ai_radar.analysis.analyzer import FakeAnalyzer
from ai_radar.analysis.models import Interest, InterestWeight
from ai_radar.analysis.pipeline import AnalysisSettings, analyze_pending
from ai_radar.articles.models import NewArticle
from ai_radar.articles.repository import ArticleRepository
from ai_radar.db import open_database
from ai_radar.interests import repository as interests_module
from ai_radar.interests.repository import (
    DuplicateInterestError,
    InterestRepository,
    TooManyInterestsError,
)
from ai_radar.main import DB_PATH_ENV, app

# --- Repository -------------------------------------------------------------


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with open_database(tmp_path / "test.db") as connection:
        yield connection


@pytest.fixture
def repo(conn: sqlite3.Connection) -> InterestRepository:
    return InterestRepository(conn)


def test_add_normalizes_whitespace_and_keeps_case(repo: InterestRepository) -> None:
    interest = repo.add("  Large   Language Models ", InterestWeight.HIGH)

    assert interest.topic == "Large Language Models"
    assert interest.weight is InterestWeight.HIGH
    assert repo.get(interest.id) == interest
    assert interest.as_input() == Interest("Large Language Models", InterestWeight.HIGH)


@pytest.mark.parametrize("duplicate", ["llm", "LLM", " Llm "])
def test_topics_are_unique_ignoring_case(
    repo: InterestRepository, duplicate: str
) -> None:
    existing = repo.add("LLM", InterestWeight.LOW)
    with pytest.raises(DuplicateInterestError):
        repo.add(duplicate, InterestWeight.HIGH)
    assert repo.list_all() == [existing]


def test_newlines_are_collapsed_like_spaces(repo: InterestRepository) -> None:
    assert repo.add("line\nbreak", InterestWeight.LOW).topic == "line break"


def test_unicode_case_folding(repo: InterestRepository) -> None:
    repo.add("Straße", InterestWeight.LOW)
    with pytest.raises(DuplicateInterestError):
        repo.add("STRASSE", InterestWeight.LOW)


@pytest.mark.parametrize("topic", ["", "   ", "x" * 101, "bad\x00topic", "tab​topic"])
def test_invalid_topics_are_rejected(repo: InterestRepository, topic: str) -> None:
    with pytest.raises(ValueError):
        repo.add(topic, InterestWeight.LOW)
    assert repo.list_all() == []


def test_interest_limit(
    repo: InterestRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(interests_module, "MAX_INTERESTS", 2)
    repo.add("a", InterestWeight.LOW)
    repo.add("b", InterestWeight.LOW)
    with pytest.raises(TooManyInterestsError):
        repo.add("c", InterestWeight.LOW)


def test_update_and_remove(repo: InterestRepository) -> None:
    interest = repo.add("agents", InterestWeight.LOW)
    other = repo.add("robotics", InterestWeight.LOW)

    renamed = repo.update(interest.id, topic="AI agents")
    reweighted = repo.update(interest.id, weight=InterestWeight.HIGH)

    assert renamed is not None and renamed.topic == "AI agents"
    assert reweighted is not None
    assert (reweighted.topic, reweighted.weight) == ("AI agents", InterestWeight.HIGH)
    with pytest.raises(DuplicateInterestError):
        repo.update(interest.id, topic="ROBOTICS")
    assert repo.update(interest.id, topic="ai AGENTS") is not None  # own topic
    assert repo.update(999, weight=InterestWeight.LOW) is None
    assert repo.remove(other.id) is True
    assert repo.remove(other.id) is False


def test_schema_rejects_unknown_weight(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO interests (topic, topic_key, weight, created_at, updated_at)"
            " VALUES ('x', 'x', 'huge', 'now', 'now')"
        )


def test_analysis_never_changes_interests(
    conn: sqlite3.Connection, repo: InterestRepository
) -> None:
    repo.add("model", InterestWeight.HIGH)
    before = repo.list_all()
    ArticleRepository(conn).add(
        NewArticle(
            source="s",
            url="https://example.com/1",
            title="New model",
            content="About a model",
            published_at=None,
            collected_at=before[0].created_at,
        )
    )

    analyze_pending(
        conn,
        FakeAnalyzer(),
        AnalysisSettings(),
        interests=tuple(i.as_input() for i in before),
    )

    assert repo.list_all() == before


# --- API ----------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv(DB_PATH_ENV, str(tmp_path / "api.db"))
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client


def create(client: TestClient, **body: Any) -> dict[str, Any]:
    response = client.post("/api/interests", json={"topic": "LLM", **body})
    assert response.status_code == 201, response.text
    return response.json()


def test_crud_flow(client: TestClient) -> None:
    assert client.get("/api/interests").json() == []

    created = create(client, topic="  Large  language models ", weight="high")
    assert created["topic"] == "Large language models"
    assert created["weight"] == "high"
    assert set(created) == {"id", "topic", "weight", "created_at", "updated_at"}
    default = create(client, topic="Robotics")
    assert default["weight"] == "medium"
    assert client.get("/api/interests").json() == [created, default]

    patched = client.patch(f"/api/interests/{created['id']}", json={"weight": "low"})
    assert patched.status_code == 200
    assert (patched.json()["topic"], patched.json()["weight"]) == (
        "Large language models",
        "low",
    )

    deleted = client.delete(f"/api/interests/{default['id']}")
    assert deleted.status_code == 204 and deleted.content == b""
    assert [i["id"] for i in client.get("/api/interests").json()] == [created["id"]]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"topic": ""},
        {"topic": "   "},
        {"topic": None},
        {"topic": "x" * 101},
        {"topic": "x" * 5000},
        {"topic": "bell\x07char"},
        {"topic": "ok", "weight": "extreme"},
        {"topic": "ok", "weight": "High"},
        {"topic": "ok", "weight": 3},
        {"topic": "ok", "id": 5},
    ],
)
def test_create_validation(client: TestClient, body: dict[str, Any]) -> None:
    assert client.post("/api/interests", json=body).status_code == 422
    assert client.get("/api/interests").json() == []


def test_create_duplicate_returns_409(client: TestClient) -> None:
    existing = create(client, topic="LLM")

    response = client.post("/api/interests", json={"topic": "llm", "weight": "high"})

    assert response.status_code == 409
    assert response.json() == {"detail": "An interest with this topic already exists"}
    assert client.get("/api/interests").json() == [existing]


def test_too_many_interests_returns_422(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(interests_module, "MAX_INTERESTS", 1)
    create(client)

    response = client.post("/api/interests", json={"topic": "other"})

    assert response.status_code == 422
    assert response.json() == {"detail": "At most 1 interests are allowed"}


@pytest.mark.parametrize(
    "body",
    [
        {"topic": None},
        {"weight": None},
        {"weight": "maybe"},
        {"topic": ""},
        {"unknown": 1},
    ],
)
def test_patch_validation(client: TestClient, body: dict[str, Any]) -> None:
    interest = create(client)
    response = client.patch(f"/api/interests/{interest['id']}", json=body)
    assert response.status_code == 422
    assert client.get("/api/interests").json() == [interest]


def test_patch_to_duplicate_topic_returns_409(client: TestClient) -> None:
    create(client, topic="LLM")
    other = create(client, topic="Robotics")

    response = client.patch(f"/api/interests/{other['id']}", json={"topic": "llm"})

    assert response.status_code == 409


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
def test_unknown_id_returns_404(client: TestClient, method: str) -> None:
    kwargs: dict[str, Any] = {"json": {"weight": "low"}} if method == "PATCH" else {}
    response = client.request(method, "/api/interests/999", **kwargs)
    assert response.status_code == 404
    assert response.json() == {"detail": "Interest not found"}


@pytest.mark.parametrize("interest_id", ["0", "-1", "abc", str(2**63)])
def test_invalid_id_returns_422(client: TestClient, interest_id: str) -> None:
    assert client.delete(f"/api/interests/{interest_id}").status_code == 422


def test_cross_site_form_post_is_not_processed(client: TestClient) -> None:
    response = client.post(
        "/api/interests",
        content=b"topic=evil",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://attacker.example",
        },
    )
    assert response.status_code == 422
    assert client.get("/api/interests").json() == []

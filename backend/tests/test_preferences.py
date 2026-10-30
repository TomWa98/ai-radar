import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_radar.analysis.analyzer import FakeAnalyzer
from ai_radar.analysis.models import (
    AnalysisInput,
    AnalysisResult,
    InterestWeight,
    LearnedPreference,
    LocalizedText,
    Usage,
)
from ai_radar.analysis.pipeline import AnalysisSettings
from ai_radar.analysis.repository import AnalysisRepository
from ai_radar.articles.models import AnalysisBasis, NewArticle
from ai_radar.articles.repository import ArticleRepository
from ai_radar.db import fetch_one, open_database
from ai_radar.feedback.repository import FeedbackRepository, Rating
from ai_radar.ingest.scheduler import ingest_and_analyze_once
from ai_radar.interests.repository import InterestRepository
from ai_radar.main import DB_PATH_ENV, app
from ai_radar.preferences import repository as preferences_module
from ai_radar.preferences.repository import LearnedTopic, PreferenceRepository

T0 = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


class StepClock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        current = self.now
        self.now += timedelta(minutes=1)
        return current


def result(topics: tuple[str, ...]) -> AnalysisResult:
    text = LocalizedText(de="Text", en="Text")
    return AnalysisResult(
        summary=text,
        primary_category="Other",
        importance=3,
        relevance=3,
        relevance_reason=text,
        topics=topics,
        basis=AnalysisBasis.EXCERPT,
        usage=Usage(model="fake", input_tokens=0, output_tokens=0, estimated_cost=0),
    )


class World:
    """A database with helpers to add analyzed articles and feedback."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.clock = StepClock()
        self.articles = ArticleRepository(conn)
        self.analyses = AnalysisRepository(conn)
        self.feedback = FeedbackRepository(conn, self.clock)
        self.preferences = PreferenceRepository(conn, self.clock)
        self._count = 0

    def article(self, *topics: str) -> int:
        self._count += 1
        stored = self.articles.add(
            NewArticle(
                source="s",
                url=f"https://example.com/{self._count}",
                title=f"Article {self._count}",
                content="Excerpt",
                published_at=None,
                collected_at=T0,
            )
        )
        assert stored is not None
        self.analyses.add(stored.id, result(topics), T0)
        # Analyzed outside the pipeline: mark it so a pass leaves it alone.
        self.conn.execute(
            "UPDATE articles SET status = 'analyzed' WHERE id = ?", (stored.id,)
        )
        return stored.id

    def rate(self, article_id: int, rating: Rating) -> None:
        self.feedback.set(article_id, rating)


@pytest.fixture
def world(tmp_path: Path) -> Iterator[World]:
    with open_database(tmp_path / "test.db") as conn:
        yield World(conn)


# --- Heuristic ----------------------------------------------------------------


def test_topic_needs_three_ratings(world: World) -> None:
    for _ in range(2):
        world.rate(world.article("agents"), Rating.RELEVANT)
    assert world.preferences.learned() == []

    world.rate(world.article("agents"), Rating.IRRELEVANT)

    assert world.preferences.learned() == [
        LearnedTopic(topic="agents", score=1, relevant=2, irrelevant=1)
    ]


def test_scores_per_topic(world: World) -> None:
    for _ in range(3):
        world.rate(world.article("agents", "crypto"), Rating.IRRELEVANT)
    world.rate(world.article("agents"), Rating.RELEVANT)
    world.rate(world.article("agents"), Rating.RELEVANT)
    world.article("agents")  # analyzed but not rated: does not count

    learned = {t.topic: t for t in world.preferences.learned()}

    assert learned["crypto"] == LearnedTopic("crypto", -3, 0, 3)
    assert learned["agents"] == LearnedTopic("agents", -1, 2, 3)
    assert [t.topic for t in world.preferences.learned()] == ["crypto", "agents"]


def test_changed_rating_counts_once(world: World) -> None:
    ids = [world.article("llm") for _ in range(3)]
    for article_id in ids:
        world.rate(article_id, Rating.IRRELEVANT)
    world.rate(ids[0], Rating.RELEVANT)  # changed, not added

    assert world.preferences.learned() == [LearnedTopic("llm", -1, 1, 2)]


def test_latest_analysis_topics_are_used(world: World) -> None:
    ids = [world.article("old") for _ in range(3)]
    for article_id in ids:
        world.analyses.add(article_id, result(("new",)), T0)  # re-analysis
        world.rate(article_id, Rating.RELEVANT)

    assert [t.topic for t in world.preferences.learned()] == ["new"]


def test_rated_articles_without_analysis_are_ignored(world: World) -> None:
    for i in range(3):
        article = world.articles.add(
            NewArticle(
                source="s",
                url=f"https://example.com/plain/{i}",
                title="t",
                content=None,
                published_at=None,
                collected_at=T0,
            )
        )
        assert article is not None
        world.rate(article.id, Rating.RELEVANT)
    assert world.preferences.learned() == []


def test_analyzer_input_is_limited(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(preferences_module, "MAX_FOR_ANALYSIS", 1)
    for _ in range(3):
        world.rate(world.article("weak"), Rating.RELEVANT)
    for _ in range(4):
        world.rate(world.article("strong"), Rating.IRRELEVANT)

    assert world.preferences.for_analysis() == (LearnedPreference("strong", -4),)


# --- Reset ----------------------------------------------------------------------


def test_reset_keeps_feedback_and_interests(world: World) -> None:
    interests = InterestRepository(world.conn)
    interests.add("agents", InterestWeight.HIGH)
    ids = [world.article("agents") for _ in range(3)]
    for article_id in ids:
        world.rate(article_id, Rating.RELEVANT)
    assert world.preferences.learned() != []
    assert world.preferences.last_reset_at() is None

    reset_at = world.preferences.reset()

    assert world.preferences.learned() == []
    assert world.preferences.last_reset_at() == reset_at
    row = fetch_one(world.conn, "SELECT COUNT(*) FROM article_feedback")
    assert row is not None and row[0] == 3  # feedback kept
    assert [i.topic for i in interests.list_all()] == ["agents"]  # interests kept


def test_feedback_after_reset_counts_again(world: World) -> None:
    ids = [world.article("agents") for _ in range(3)]
    for article_id in ids:
        world.rate(article_id, Rating.RELEVANT)
    world.preferences.reset()

    for article_id in ids:
        world.rate(article_id, Rating.IRRELEVANT)

    assert world.preferences.learned() == [LearnedTopic("agents", -3, 0, 3)]


# --- Analysis input -------------------------------------------------------------


def test_new_analyses_get_learned_preferences(tmp_path: Path) -> None:
    db = tmp_path / "radar.db"
    with open_database(db) as conn:
        world = World(conn)
        old_ids = [world.article("agents") for _ in range(3)]
        for article_id in old_ids:
            world.rate(article_id, Rating.RELEVANT)
        before = [world.analyses.latest_for_article(i) for i in old_ids]
        new = world.articles.add(
            NewArticle(
                source="s",
                url="https://example.com/new",
                title="New agents framework",
                content="About agents",
                published_at=None,
                collected_at=T0,
            )
        )
        assert new is not None
    seen: list[AnalysisInput] = []

    class Recording:
        def analyze(self, item: AnalysisInput) -> AnalysisResult:
            seen.append(item)
            return FakeAnalyzer().analyze(item)

    ingest_and_analyze_once(db, Recording(), AnalysisSettings())  # no feeds

    assert [i.title for i in seen] == ["New agents framework"]
    assert seen[0].learned_preferences == (LearnedPreference("agents", 3),)
    assert seen[0].interests == ()
    with open_database(db) as conn:
        analyses = AnalysisRepository(conn)
        # Existing analyses are not recomputed.
        assert [analyses.latest_for_article(i) for i in old_ids] == before


# --- API ------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "api.db"
    monkeypatch.setenv(DB_PATH_ENV, str(path))
    return path


@pytest.fixture
def client(db_path: Path) -> Iterator[TestClient]:
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client


def test_api_lists_and_resets(client: TestClient, db_path: Path) -> None:
    assert client.get("/api/preferences").json() == {
        "learned": [],
        "last_reset_at": None,
    }
    with open_database(db_path) as conn:
        world = World(conn)
        InterestRepository(conn).add("robotics", InterestWeight.LOW)
        for rating in (Rating.RELEVANT, Rating.RELEVANT, Rating.IRRELEVANT):
            world.rate(world.article("agents"), rating)

    body = client.get("/api/preferences").json()
    assert body["learned"] == [
        {"topic": "agents", "score": 1, "relevant": 2, "irrelevant": 1, "ratings": 3}
    ]
    assert "robotics" not in str(body)  # manual interests are separate

    response = client.delete("/api/preferences")

    assert response.status_code == 204 and response.content == b""
    after = client.get("/api/preferences").json()
    assert after["learned"] == [] and after["last_reset_at"] is not None
    assert [i["topic"] for i in client.get("/api/interests").json()] == ["robotics"]


def test_reset_requires_local_host(client: TestClient) -> None:
    response = client.delete("/api/preferences", headers={"Host": "attacker.example"})
    assert response.status_code == 400
    assert client.get("/api/preferences").json()["last_reset_at"] is None

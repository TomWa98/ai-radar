import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ai_radar.analysis.models import AnalysisResult, LocalizedText, Usage
from ai_radar.analysis.repository import AnalysisRepository
from ai_radar.articles.models import AnalysisBasis, NewArticle
from ai_radar.articles.repository import ArticleRepository
from ai_radar.db import open_database
from ai_radar.feedback.repository import FeedbackRepository, Rating
from ai_radar.main import DB_PATH_ENV, app

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def result(
    primary: str, relevance: int, secondary: tuple[str, ...] = ()
) -> AnalysisResult:
    return AnalysisResult(
        summary=LocalizedText(de=f"Zusammenfassung {primary}", en=f"Summary {primary}"),
        primary_category=primary,
        secondary_categories=secondary,
        importance=3,
        relevance=relevance,
        relevance_reason=LocalizedText(de="Grund", en="Reason"),
        topics=("llm",),
        basis=AnalysisBasis.EXCERPT,
        usage=Usage(model="fake", input_tokens=0, output_tokens=0, estimated_cost=0),
    )


class World:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.articles = ArticleRepository(conn)
        self.analyses = AnalysisRepository(conn)

    def article(
        self,
        slug: str,
        published: datetime | None,
        analysis: AnalysisResult | None = None,
        analyzed_at: datetime = T0,
    ) -> int:
        stored = self.articles.add(
            NewArticle(
                source="Feed",
                url=f"https://example.com/{slug}",
                title=f"Title {slug}",
                content=f"<p>Excerpt {slug}</p>",
                published_at=published,
                collected_at=T0,
            )
        )
        assert stored is not None
        if analysis is not None:
            self.analyses.add(stored.id, analysis, analyzed_at)
            self.conn.execute(
                "UPDATE articles SET status = 'analyzed' WHERE id = ?", (stored.id,)
            )
        return stored.id


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
def ids(client: TestClient, db_path: Path) -> dict[str, int]:
    with open_database(db_path) as conn:
        world = World(conn)
        return {
            "release": world.article(
                "release", T0 + timedelta(days=1), result("Releases", 2, ("Features",))
            ),
            "security": world.article(
                "security", T0 + timedelta(days=3), result("Security", 5)
            ),
            "usecase": world.article(
                "usecase", T0 + timedelta(days=2), result("Use Cases", 4)
            ),
            "pending": world.article("pending", T0 + timedelta(days=4)),
            "undated": world.article("undated", None),  # sorted by collection date
        }


def titles(response: Any) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["title"] for item in response.json()["items"]]


def test_default_lists_all_articles_newest_first(
    client: TestClient, ids: dict[str, int]
) -> None:
    response = client.get("/api/articles")

    assert titles(response) == [
        "Title pending",
        "Title security",
        "Title usecase",
        "Title release",
        "Title undated",
    ]
    assert response.json()["total"] == 5


def test_item_shape_and_language(client: TestClient, ids: dict[str, int]) -> None:
    de = client.get("/api/articles", params={"lang": "de"}).json()["items"]
    en = client.get("/api/articles", params={"lang": "en"}).json()["items"]
    by_title = {item["title"]: item for item in de}
    en_by_title = {item["title"]: item for item in en}

    release = by_title["Title release"]
    assert release["analysis"]["summary"] == "Zusammenfassung Releases"
    assert en_by_title["Title release"]["analysis"]["summary"] == "Summary Releases"
    assert en_by_title["Title release"]["analysis"]["relevance_reason"] == "Reason"
    # Categories and scores do not depend on the language.
    for field in (
        "primary_category",
        "secondary_categories",
        "importance",
        "relevance",
    ):
        assert (
            release["analysis"][field]
            == en_by_title["Title release"]["analysis"][field]
        )
    assert release["excerpt"] == "<p>Excerpt release</p>"  # raw, untrusted
    assert release["status"] == "analyzed"
    assert release["feedback"] is None
    pending = by_title["Title pending"]
    assert pending["status"] == "new" and pending["analysis"] is None


def test_category_filter_matches_primary_and_secondary(
    client: TestClient, ids: dict[str, int]
) -> None:
    assert titles(client.get("/api/articles", params={"category": "Security"})) == [
        "Title security"
    ]
    assert titles(client.get("/api/articles", params={"category": "Features"})) == [
        "Title release"
    ]
    assert titles(client.get("/api/articles", params={"category": "Other"})) == []


def test_min_relevance_filter(client: TestClient, ids: dict[str, int]) -> None:
    response = client.get("/api/articles", params={"min_relevance": 4})
    assert titles(response) == ["Title security", "Title usecase"]


def test_publication_period_filter(client: TestClient, ids: dict[str, int]) -> None:
    response = client.get(
        "/api/articles",
        params={
            "published_from": (T0 + timedelta(days=2)).isoformat(),
            "published_to": (T0 + timedelta(days=3)).isoformat(),
        },
    )
    assert titles(response) == ["Title security", "Title usecase"]


def test_sort_by_relevance_puts_unanalyzed_last(
    client: TestClient, ids: dict[str, int]
) -> None:
    response = client.get("/api/articles", params={"sort": "relevance"})
    assert titles(response) == [
        "Title security",
        "Title usecase",
        "Title release",
        "Title pending",
        "Title undated",
    ]


def test_pagination(client: TestClient, ids: dict[str, int]) -> None:
    first = client.get("/api/articles", params={"limit": 2}).json()
    second = client.get("/api/articles", params={"limit": 2, "offset": 2}).json()
    beyond = client.get("/api/articles", params={"limit": 2, "offset": 50}).json()

    assert [i["title"] for i in first["items"]] == ["Title pending", "Title security"]
    assert [i["title"] for i in second["items"]] == ["Title usecase", "Title release"]
    assert (first["total"], first["limit"], first["offset"]) == (5, 2, 0)
    assert beyond["items"] == [] and beyond["total"] == 5


def test_empty_database(client: TestClient) -> None:
    body = client.get("/api/articles").json()
    assert (body["items"], body["total"]) == ([], 0)


@pytest.mark.parametrize(
    "params",
    [
        {"lang": "fr"},
        {"category": "Gossip"},
        {"category": "security"},
        {"min_relevance": 0},
        {"min_relevance": 6},
        {"min_relevance": "high"},
        {"sort": "random"},
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"offset": 10_000_000},
        {"published_from": "yesterday"},
        {"published_from": "2026-10-01T12:00:00"},  # no timezone
        {"since": "2026-10-01T12:00:00"},
        {
            "published_from": "2026-10-05T00:00:00Z",
            "published_to": "2026-10-01T00:00:00Z",
        },
    ],
)
def test_invalid_parameters_return_422(
    client: TestClient, params: dict[str, Any]
) -> None:
    assert client.get("/api/articles", params=params).status_code == 422


def test_sql_metacharacters_are_just_data(
    client: TestClient, ids: dict[str, int]
) -> None:
    response = client.get("/api/articles", params={"category": "Other' OR '1'='1"})
    assert response.status_code == 422


def test_polling_with_since(
    client: TestClient, ids: dict[str, int], db_path: Path
) -> None:
    first = client.get("/api/articles").json()
    next_since = first["next_since"]
    assert (
        client.get("/api/articles", params={"since": next_since}).json()["items"] == []
    )

    with open_database(db_path) as conn:
        FeedbackRepository(conn).set(ids["usecase"], Rating.RELEVANT)
        world = World(conn)
        world.article("fresh", T0)  # collected_at is T0, but see below
        conn.execute(
            "UPDATE articles SET collected_at = ? WHERE url LIKE '%/fresh'",
            ((datetime.now(UTC)).isoformat(),),
        )

    changed = client.get("/api/articles", params={"since": next_since}).json()

    assert sorted(i["title"] for i in changed["items"]) == [
        "Title fresh",
        "Title usecase",
    ]
    usecase = next(i for i in changed["items"] if i["title"] == "Title usecase")
    assert usecase["feedback"] == "relevant"
    assert changed["total"] == 2


def test_next_since_overlaps_the_request(client: TestClient) -> None:
    before = datetime.now(UTC)
    body = client.get("/api/articles").json()
    next_since = datetime.fromisoformat(body["next_since"])
    assert next_since <= before


def test_new_analysis_shows_up_when_polling(
    client: TestClient, ids: dict[str, int], db_path: Path
) -> None:
    since = client.get("/api/articles").json()["next_since"]
    with open_database(db_path) as conn:
        AnalysisRepository(conn).add(
            ids["pending"], result("Other", 1), datetime.now(UTC)
        )

    changed = client.get("/api/articles", params={"since": since}).json()["items"]

    assert [i["title"] for i in changed] == ["Title pending"]
    assert changed[0]["analysis"]["primary_category"] == "Other"


def test_failed_analysis_shows_up_when_polling(
    client: TestClient, ids: dict[str, int], db_path: Path
) -> None:
    with open_database(db_path) as conn:
        articles = ArticleRepository(conn)
        claimed_at = datetime.now(UTC) - timedelta(minutes=5)
        articles.claim_for_analysis(10, 3, claimed_at, claimed_at)
    since = client.get("/api/articles").json()["next_since"]

    with open_database(db_path) as conn:
        ArticleRepository(conn).mark_failed(ids["pending"], "Provider error")

    changed = client.get("/api/articles", params={"since": since}).json()["items"]
    pending = next(i for i in changed if i["title"] == "Title pending")
    assert pending["status"] == "failed"
    assert pending["analysis_error"] == "Provider error"

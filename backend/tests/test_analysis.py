import sqlite3
from collections.abc import Iterator
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from ai_radar.analysis.analyzer import Analyzer, FakeAnalyzer
from ai_radar.analysis.models import (
    AnalysisInput,
    AnalysisResult,
    Category,
    Interest,
    InterestWeight,
    LearnedPreference,
)
from ai_radar.analysis.repository import AnalysisRepository
from ai_radar.articles.models import AnalysisBasis, NewArticle
from ai_radar.articles.repository import ArticleRepository
from ai_radar.db import MIGRATIONS, connect, fetch_one, init_schema, open_database

ANALYZED_AT = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


def valid_result(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "summary": {"de": "Neues Modell veröffentlicht.", "en": "New model released."},
        "primary_category": "Releases",
        "secondary_categories": ["Features", "Use Cases"],
        "importance": 4,
        "relevance": 5,
        "relevance_reason": {"de": "Passt zu LLMs.", "en": "Matches LLMs."},
        "topics": ["LLM", "openai", "llm"],
        "basis": "full_text",
        "usage": {
            "model": "gpt-test",
            "input_tokens": 1200,
            "output_tokens": 300,
            "estimated_cost": 0.0042,
        },
    }
    data.update(overrides)
    return data


def item(**overrides: Any) -> AnalysisInput:
    fields: dict[str, Any] = {
        "title": "OpenAI releases a new reasoning model",
        "text": "The model improves coding and agent workflows.",
        "basis": AnalysisBasis.EXCERPT,
    }
    fields.update(overrides)
    return AnalysisInput(**fields)


# --- Result validation ---------------------------------------------------


def test_valid_result_is_accepted() -> None:
    result = AnalysisResult.model_validate(valid_result())

    assert result.primary_category is Category.RELEASES
    assert result.secondary_categories == (Category.FEATURES, Category.USE_CASES)
    assert (result.importance, result.relevance) == (4, 5)
    assert result.summary.de and result.summary.en
    assert result.topics == ("llm", "openai")  # normalized and de-duplicated
    assert result.basis is AnalysisBasis.FULL_TEXT
    assert result.usage.input_tokens == 1200


def test_secondary_categories_are_optional() -> None:
    result = AnalysisResult.model_validate(valid_result(secondary_categories=[]))
    assert result.secondary_categories == ()


@pytest.mark.parametrize(
    "overrides",
    [
        {"primary_category": "Gossip"},
        {"primary_category": "releases"},
        {"secondary_categories": ["Releases"]},  # same as primary
        {"secondary_categories": ["Features", "Features"]},
        {"secondary_categories": ["Rumors"]},
        {"importance": 0},
        {"importance": 6},
        {"relevance": -1},
        {"relevance": 2.5},
        {"relevance": "3"},
        {"relevance": True},
        {"summary": {"de": "Nur Deutsch"}},
        {"summary": {"en": "English only"}},
        {"summary": {"de": "   ", "en": "Blank German"}},
        {"relevance_reason": {"de": "Grund"}},
        {"summary": {"de": "x", "en": "y", "fr": "z"}},
        {"basis": "guess"},
        {"topics": ["x" * 51]},
        {"topics": [f"t{i}" for i in range(11)]},
        {
            "usage": {
                "model": "m",
                "input_tokens": -1,
                "output_tokens": 0,
                "estimated_cost": 0,
            }
        },
        {
            "usage": {
                "model": "m",
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost": float("nan"),
            }
        },
        {"extra_field": "ignored?"},
    ],
)
def test_invalid_results_are_rejected(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(valid_result(**overrides))


@pytest.mark.parametrize("field", ["summary", "relevance_reason", "basis", "usage"])
def test_missing_fields_are_rejected(field: str) -> None:
    data = valid_result()
    del data[field]
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(data)


# --- Analyzer ------------------------------------------------------------


def test_fake_analyzer_satisfies_interface() -> None:
    analyzer: Analyzer = FakeAnalyzer()
    assert isinstance(analyzer.analyze(item()), AnalysisResult)


def test_fake_analyzer_is_deterministic() -> None:
    interests = (Interest("agent", InterestWeight.HIGH),)
    first = FakeAnalyzer().analyze(item(interests=interests))
    second = FakeAnalyzer().analyze(item(interests=interests))

    assert first == second
    assert first.basis is AnalysisBasis.EXCERPT
    assert first.usage.model == "fake" and first.usage.estimated_cost == 0


def test_fake_analyzer_differs_for_different_articles() -> None:
    results = {
        FakeAnalyzer().analyze(item(title=f"Article {i}")).model_dump_json()
        for i in range(20)
    }
    assert len(results) > 1


def test_interests_and_learned_preferences_are_separate_inputs() -> None:
    analyzer = FakeAnalyzer()
    plain = analyzer.analyze(item())
    with_interest = analyzer.analyze(
        item(interests=(Interest("agent", InterestWeight.HIGH),))
    )
    with_learned = analyzer.analyze(
        item(learned_preferences=(LearnedPreference("coding", 3),))
    )
    disliked = analyzer.analyze(
        item(
            interests=(Interest("agent", InterestWeight.MEDIUM),),
            learned_preferences=(LearnedPreference("coding", -4),),
        )
    )

    assert plain.relevance == 1
    assert with_interest.relevance == 4
    assert "agent" in with_interest.relevance_reason.en
    assert with_learned.relevance == 2
    assert disliked.relevance == 2  # 1 + 2 (interest) - 1 (learned)
    # Scores of the article itself do not depend on the profile.
    assert plain.importance == with_interest.importance == with_learned.importance
    assert plain.primary_category == with_interest.primary_category


def test_relevance_is_capped() -> None:
    interests = tuple(
        Interest(topic, InterestWeight.HIGH) for topic in ("openai", "model", "coding")
    )
    assert FakeAnalyzer().analyze(item(interests=interests)).relevance == 5


def test_fake_analyzer_handles_awkward_input() -> None:
    result = FakeAnalyzer().analyze(
        item(
            title="   ",
            text="",
            interests=(Interest("", InterestWeight.HIGH),),
        )
    )
    assert result.relevance == 1
    long_title = FakeAnalyzer().analyze(item(title="a" * 5000 + " " + "b" * 80))
    assert len(long_title.summary.de) <= 2000
    assert all(len(topic) <= 50 for topic in long_title.topics)


# --- Persistence ---------------------------------------------------------


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with open_database(tmp_path / "test.db") as connection:
        yield connection


def add_article(conn: sqlite3.Connection) -> int:
    article = ArticleRepository(conn).add(
        NewArticle(
            source="Example",
            url="https://example.com/1",
            title="Title",
            content="Excerpt",
            published_at=None,
            collected_at=ANALYZED_AT,
        )
    )
    assert article is not None
    return article.id


def test_analysis_round_trip(conn: sqlite3.Connection) -> None:
    article_id = add_article(conn)
    result = AnalysisResult.model_validate(valid_result())
    repo = AnalysisRepository(conn)

    stored = repo.add(article_id, result, ANALYZED_AT)

    assert stored.result == result
    assert stored.article_id == article_id
    assert stored.analyzed_at == ANALYZED_AT
    assert repo.latest_for_article(article_id) == stored
    assert repo.latest_for_article(article_id + 1) is None


def test_texts_are_stored_per_language(conn: sqlite3.Connection) -> None:
    article_id = add_article(conn)
    stored = AnalysisRepository(conn).add(
        article_id, AnalysisResult.model_validate(valid_result()), ANALYZED_AT
    )

    rows = conn.execute(
        "SELECT language, summary FROM analysis_texts WHERE analysis_id = ? "
        "ORDER BY language",
        (stored.id,),
    ).fetchall()
    assert [tuple(row) for row in rows] == [
        ("de", "Neues Modell veröffentlicht."),
        ("en", "New model released."),
    ]
    scores = fetch_one(
        conn,
        "SELECT primary_category, importance, relevance FROM analyses WHERE id = ?",
        (stored.id,),
    )
    assert scores is not None and tuple(scores) == ("Releases", 4, 5)


def test_reanalysis_keeps_history(conn: sqlite3.Connection) -> None:
    article_id = add_article(conn)
    repo = AnalysisRepository(conn)
    first = repo.add(
        article_id, AnalysisResult.model_validate(valid_result()), ANALYZED_AT
    )
    second = repo.add(
        article_id,
        AnalysisResult.model_validate(valid_result(relevance=2)),
        ANALYZED_AT,
    )

    assert repo.latest_for_article(article_id) == second
    assert repo.get(first.id) == first


def test_analysis_does_not_change_article(conn: sqlite3.Connection) -> None:
    article_id = add_article(conn)
    articles = ArticleRepository(conn)
    before = articles.get_by_id(article_id)

    AnalysisRepository(conn).add(
        article_id, FakeAnalyzer().analyze(item()), ANALYZED_AT
    )

    assert articles.get_by_id(article_id) == before


def test_unvalidated_result_is_rejected_on_save(conn: sqlite3.Connection) -> None:
    article_id = add_article(conn)
    bogus = AnalysisResult.model_construct(**valid_result(importance=9))

    with pytest.raises(ValidationError):
        AnalysisRepository(conn).add(article_id, bogus, ANALYZED_AT)
    row = fetch_one(conn, "SELECT COUNT(*) FROM analyses")
    assert row is not None and row[0] == 0


def test_analysis_for_unknown_article_is_rejected(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="Unknown article"):
        AnalysisRepository(conn).add(42, FakeAnalyzer().analyze(item()), ANALYZED_AT)
    row = fetch_one(conn, "SELECT COUNT(*) FROM analyses")
    assert row is not None and row[0] == 0


def test_naive_timestamp_is_rejected(conn: sqlite3.Connection) -> None:
    article_id = add_article(conn)
    with pytest.raises(ValueError, match="timezone"):
        AnalysisRepository(conn).add(
            article_id, FakeAnalyzer().analyze(item()), datetime(2026, 10, 30)
        )


def test_schema_rejects_invalid_scores(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO analyses (article_id, primary_category, importance,
                relevance, analysis_basis, model, input_tokens, output_tokens,
                estimated_cost, analyzed_at)
            VALUES (1, 'Releases', 6, 3, 'excerpt', 'm', 0, 0, 0, 'x')
            """
        )


def test_migration_keeps_existing_articles(tmp_path: Path) -> None:
    path = tmp_path / "test.db"
    with closing(connect(path)) as conn:
        init_schema(conn, MIGRATIONS[:-1])
        conn.execute(
            """
            INSERT INTO articles (source, url, normalized_url, title, content,
                                  collected_at)
            VALUES ('s', 'https://e.com/a', 'https://e.com/a', 't', 'c',
                    '2026-10-30T12:00:00+00:00')
            """
        )

    with open_database(path) as conn:
        article = ArticleRepository(conn).get_by_id(1)
        assert article is not None and article.content == "c"
        assert AnalysisRepository(conn).latest_for_article(1) is None

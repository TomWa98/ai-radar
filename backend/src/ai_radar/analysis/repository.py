"""Database access for analyses.

An article may be analyzed more than once (e.g. after a retry); every analysis
is kept and the latest one counts. Articles themselves are never changed here.
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from ai_radar.analysis.models import AnalysisResult
from ai_radar.db import fetch_one, transaction

LANGUAGES = ("de", "en")


@dataclass(frozen=True, slots=True)
class StoredAnalysis:
    id: int
    article_id: int
    analyzed_at: datetime
    result: AnalysisResult


class AnalysisRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(
        self, article_id: int, result: AnalysisResult, analyzed_at: datetime
    ) -> StoredAnalysis:
        """Store a validated result for an existing article.

        Raises ``ValueError`` if the article does not exist.
        """
        if analyzed_at.utcoffset() is None:
            raise ValueError("analyzed_at must be timezone-aware")
        # Re-validate: a model built with model_construct() skips validation.
        result = AnalysisResult.model_validate(result.model_dump(warnings=False))
        with transaction(self._conn):
            if (
                fetch_one(
                    self._conn, "SELECT 1 FROM articles WHERE id = ?", (article_id,)
                )
                is None
            ):
                raise ValueError(f"Unknown article: {article_id}")
            row = fetch_one(
                self._conn,
                """
                INSERT INTO analyses
                    (article_id, primary_category, secondary_categories,
                     importance, relevance, topics, analysis_basis, model,
                     input_tokens, output_tokens, estimated_cost, analyzed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                (
                    article_id,
                    result.primary_category,
                    json.dumps(list(result.secondary_categories)),
                    result.importance,
                    result.relevance,
                    json.dumps(list(result.topics)),
                    result.basis,
                    result.usage.model,
                    result.usage.input_tokens,
                    result.usage.output_tokens,
                    result.usage.estimated_cost,
                    analyzed_at.astimezone(UTC).isoformat(),
                ),
            )
            assert row is not None
            analysis_id = row["id"]
            self._conn.executemany(
                """
                INSERT INTO analysis_texts
                    (analysis_id, language, summary, relevance_reason)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        analysis_id,
                        language,
                        getattr(result.summary, language),
                        getattr(result.relevance_reason, language),
                    )
                    for language in LANGUAGES
                ],
            )
        stored = self.get(analysis_id)
        assert stored is not None
        return stored

    def get(self, analysis_id: int) -> StoredAnalysis | None:
        row = fetch_one(
            self._conn, "SELECT * FROM analyses WHERE id = ?", (analysis_id,)
        )
        return None if row is None else self._load(row)

    def latest_for_article(self, article_id: int) -> StoredAnalysis | None:
        row = fetch_one(
            self._conn,
            "SELECT * FROM analyses WHERE article_id = ? ORDER BY id DESC LIMIT 1",
            (article_id,),
        )
        return None if row is None else self._load(row)

    def _load(self, row: sqlite3.Row) -> StoredAnalysis:
        texts = {
            text["language"]: text
            for text in self._conn.execute(
                "SELECT * FROM analysis_texts WHERE analysis_id = ?", (row["id"],)
            ).fetchall()
        }
        result = AnalysisResult.model_validate(
            {
                "summary": {lang: texts[lang]["summary"] for lang in LANGUAGES},
                "primary_category": row["primary_category"],
                "secondary_categories": json.loads(row["secondary_categories"]),
                "importance": row["importance"],
                "relevance": row["relevance"],
                "relevance_reason": {
                    lang: texts[lang]["relevance_reason"] for lang in LANGUAGES
                },
                "topics": json.loads(row["topics"]),
                "basis": row["analysis_basis"],
                "usage": {
                    "model": row["model"],
                    "input_tokens": row["input_tokens"],
                    "output_tokens": row["output_tokens"],
                    "estimated_cost": row["estimated_cost"],
                },
            }
        )
        return StoredAnalysis(
            id=row["id"],
            article_id=row["article_id"],
            analyzed_at=datetime.fromisoformat(row["analyzed_at"]),
            result=result,
        )

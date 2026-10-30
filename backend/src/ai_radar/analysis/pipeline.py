"""Analysis of collected articles after each fetch pass (FR-13, FR-33).

Articles move ``new`` → ``processing`` → ``analyzed`` or ``failed``. A failed
article is retried in later passes until it reaches the configured number of
attempts; one failing article never stops the others.

Claiming is atomic (one ``BEGIN IMMEDIATE`` transaction), so no article is
analyzed twice at the same time. Analyzer calls run in a bounded thread pool;
all database writes happen on the calling thread with its own connection.
Articles left in ``processing`` by a crash are returned to ``new`` at startup.

By default the deterministic FakeAnalyzer is used, so no paid API is called
unless a real analyzer is configured explicitly (D5).
"""

import logging
import sqlite3
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import ValidationError

from ai_radar.analysis.analyzer import AnalysisError, Analyzer, FakeAnalyzer
from ai_radar.analysis.models import (
    AnalysisInput,
    AnalysisResult,
    Interest,
    LearnedPreference,
)
from ai_radar.analysis.repository import AnalysisRepository
from ai_radar.articles.models import AnalysisBasis, Article
from ai_radar.articles.repository import ArticleRepository

logger = logging.getLogger(__name__)

ANALYZER_ENV = "AI_RADAR_ANALYZER"
MAX_ATTEMPTS_ENV = "AI_RADAR_ANALYSIS_MAX_ATTEMPTS"
CONCURRENCY_ENV = "AI_RADAR_ANALYSIS_CONCURRENCY"

DEFAULT_ANALYZER = "fake"
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_CONCURRENCY = 2

Clock = Callable[[], datetime]

_ANALYZERS: dict[str, Callable[[], Analyzer]] = {"fake": FakeAnalyzer}


def _now() -> datetime:
    return datetime.now(UTC)


def _positive_int(environ: Mapping[str, str], name: str, default: int) -> int:
    raw = environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be a positive integer") from None
    if value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class AnalysisSettings:
    analyzer: str = DEFAULT_ANALYZER
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    concurrency: int = DEFAULT_CONCURRENCY

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> "AnalysisSettings":
        """Read the settings; raise ``ValueError`` for invalid values."""
        analyzer = environ.get(ANALYZER_ENV, "").strip().lower() or DEFAULT_ANALYZER
        if analyzer not in _ANALYZERS:
            raise ValueError(f"Unknown analyzer: {analyzer!r}")
        return cls(
            analyzer=analyzer,
            max_attempts=_positive_int(environ, MAX_ATTEMPTS_ENV, DEFAULT_MAX_ATTEMPTS),
            concurrency=_positive_int(environ, CONCURRENCY_ENV, DEFAULT_CONCURRENCY),
        )

    def create_analyzer(self) -> Analyzer:
        return _ANALYZERS[self.analyzer]()


@dataclass(frozen=True, slots=True)
class PipelineStats:
    analyzed: int = 0
    failed: int = 0


def _input_for(
    article: Article,
    interests: tuple[Interest, ...],
    learned_preferences: tuple[LearnedPreference, ...],
) -> AnalysisInput:
    basis = article.analysis_basis or AnalysisBasis.EXCERPT
    if basis is AnalysisBasis.FULL_TEXT and article.full_text:
        text = article.full_text
    else:
        basis = AnalysisBasis.EXCERPT
        text = article.content or ""
    return AnalysisInput(
        title=article.title,
        text=text,
        basis=basis,
        interests=interests,
        learned_preferences=learned_preferences,
    )


def _error_message(exc: BaseException) -> str:
    """A storable message: never secrets or article text."""
    if isinstance(exc, AnalysisError):
        return str(exc) or "Analysis failed"
    if isinstance(exc, ValidationError):
        return "Invalid analyzer result"
    return f"Unexpected {type(exc).__name__}"


def analyze_pending(
    conn: sqlite3.Connection,
    analyzer: Analyzer,
    settings: AnalysisSettings,
    *,
    interests: tuple[Interest, ...] = (),
    learned_preferences: tuple[LearnedPreference, ...] = (),
    clock: Clock = _now,
) -> PipelineStats:
    """Analyze all claimable articles; return how many succeeded and failed.

    Articles that fail in this pass are not retried before the next pass.
    """
    articles = ArticleRepository(conn)
    analyses = AnalysisRepository(conn)
    started = clock()
    analyzed = failed = 0
    with ThreadPoolExecutor(
        max_workers=settings.concurrency, thread_name_prefix="analysis"
    ) as pool:
        while batch := articles.claim_for_analysis(
            settings.concurrency, settings.max_attempts, clock(), started
        ):
            jobs: list[tuple[Article, AnalysisInput, Future[AnalysisResult]]] = []
            for article in batch:
                item = _input_for(article, interests, learned_preferences)
                jobs.append((article, item, pool.submit(analyzer.analyze, item)))
            for article, item, job in jobs:
                try:
                    result = job.result()
                    if result.basis is not item.basis:
                        raise AnalysisError("Analysis basis does not match the input")
                    analyses.add(article.id, result, clock())
                except Exception as exc:
                    message = _error_message(exc)
                    logger.warning(
                        "Analysis of article %d failed: %s", article.id, message
                    )
                    articles.mark_failed(article.id, message)
                    failed += 1
                else:
                    articles.mark_analyzed(article.id)
                    analyzed += 1
    if analyzed or failed:
        logger.info("Analysis pass: %d analyzed, %d failed", analyzed, failed)
    return PipelineStats(analyzed=analyzed, failed=failed)

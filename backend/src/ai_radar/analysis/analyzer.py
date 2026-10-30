"""Provider-independent analyzer interface and the deterministic FakeAnalyzer."""

import hashlib
import re
from typing import Protocol

from ai_radar.analysis.models import (
    MAX_TEXT_LENGTH,
    MAX_TOPICS,
    AnalysisInput,
    AnalysisResult,
    Category,
    InterestWeight,
    LocalizedText,
    Usage,
)


class AnalysisError(Exception):
    """An analysis failed; the message is safe to store and show.

    It must never contain secrets or article text. Analyzers raise it for
    expected failures; any other exception is recorded by type only.
    """


class Analyzer(Protocol):
    def analyze(self, item: AnalysisInput) -> AnalysisResult:
        """Analyze one article; raise on failure, never return partial results."""
        ...


_WEIGHT_POINTS = {
    InterestWeight.LOW: 1,
    InterestWeight.MEDIUM: 2,
    InterestWeight.HIGH: 3,
}
_WORD = re.compile(r"[^\W\d_]{4,}")


def _mentions(text: str, topic: str) -> bool:
    topic = topic.strip().lower()
    return bool(topic) and topic in text


class FakeAnalyzer:
    """Deterministic analyzer for tests and default operation (D5).

    The same input always gives the same result: categories and importance
    are derived from a hash of the article, relevance from simple keyword
    matches against the interests and learned preferences. No network access.
    """

    MODEL = "fake"

    def analyze(self, item: AnalysisInput) -> AnalysisResult:
        digest = hashlib.sha256(
            "\x00".join((item.title, item.text, item.basis)).encode()
        ).digest()
        categories = list(Category)
        primary = categories[digest[0] % len(categories)]
        others = [c for c in categories if c is not primary]
        secondary = (others[digest[1] % len(others)],) if digest[1] % 2 else ()

        haystack = f"{item.title}\n{item.text}".lower()
        matched = [i for i in item.interests if _mentions(haystack, i.topic)]
        learned = [
            p
            for p in item.learned_preferences
            if p.score != 0 and _mentions(haystack, p.topic)
        ]
        points = sum(_WEIGHT_POINTS[i.weight] for i in matched)
        points += sum(1 if p.score > 0 else -1 for p in learned)
        relevance = max(1, min(5, 1 + points))

        names = ", ".join(i.topic.strip() for i in matched)
        if names:
            reason_de = f"Passende Interessen: {names}."
            reason_en = f"Matching interests: {names}."
        else:
            reason_de = "Keine passenden Interessen."
            reason_en = "No matching interests."
        words = (word.lower()[:50] for word in _WORD.findall(item.title))
        topics = tuple(dict.fromkeys(words))[:MAX_TOPICS]
        title = item.title.strip()
        return AnalysisResult(
            summary=LocalizedText(
                de=f"Zusammenfassung (Fake): {title or '(ohne Titel)'}"[
                    :MAX_TEXT_LENGTH
                ],
                en=f"Summary (fake): {title or '(untitled)'}"[:MAX_TEXT_LENGTH],
            ),
            primary_category=primary,
            secondary_categories=secondary,
            importance=1 + digest[2] % 5,
            relevance=relevance,
            relevance_reason=LocalizedText(
                de=reason_de[:MAX_TEXT_LENGTH], en=reason_en[:MAX_TEXT_LENGTH]
            ),
            topics=topics,
            basis=item.basis,
            usage=Usage(
                model=self.MODEL, input_tokens=0, output_tokens=0, estimated_cost=0.0
            ),
        )

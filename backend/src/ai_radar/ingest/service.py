"""Ingest feeds into the article store, isolating per-feed failures."""

import logging
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

from ai_radar.articles.models import Article
from ai_radar.articles.repository import ArticleRepository
from ai_radar.feeds.repository import FeedRepository
from ai_radar.ingest.fetch import FetchedFeed, FetchError
from ai_radar.ingest.fulltext import PageFetcher, extract_full_text
from ai_radar.ingest.parse import FeedParseError, parse_feed

logger = logging.getLogger(__name__)

Fetcher = Callable[[str], FetchedFeed]
Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class FeedResult:
    url: str  # redacted, safe to log or print
    new: int = 0
    duplicates: int = 0
    skipped: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def redact_url(url: str) -> str:
    """Remove embedded credentials from ``url`` for logging."""
    try:
        parts = urlsplit(url)
        if "@" not in parts.netloc:
            return url
        return urlunsplit(parts._replace(netloc=parts.netloc.rpartition("@")[2]))
    except ValueError:
        return "<invalid URL>"


def _now() -> datetime:
    return datetime.now(UTC)


def ingest_feed(
    url: str,
    fetch: Fetcher,
    repository: ArticleRepository,
    clock: Clock = _now,
    feed_id: int | None = None,
    fetch_page: PageFetcher | None = None,
) -> FeedResult:
    """Fetch, parse, and store one feed; errors propagate to the caller.

    Relative links are resolved against the final URL after redirects. New
    articles are linked to ``feed_id``; already stored ones keep their link.
    With ``fetch_page`` (feed opt-in, D3) the full text of each new article is
    fetched; otherwise no article page is requested.
    """
    fetched = fetch(url)
    parsed = parse_feed(fetched.content, fetched.url, clock())
    new = duplicates = 0
    for article in parsed.articles:
        stored = repository.add(replace(article, feed_id=feed_id))
        if stored is None:
            duplicates += 1
            continue
        new += 1
        if fetch_page is not None:
            _add_full_text(stored, fetch_page, repository)
    return FeedResult(
        url=redact_url(url), new=new, duplicates=duplicates, skipped=parsed.skipped
    )


def _add_full_text(
    article: Article, fetch_page: PageFetcher, repository: ArticleRepository
) -> None:
    """Store the article's full text if available; else it keeps the excerpt."""
    try:
        text = extract_full_text(article.url, fetch_page)
    except Exception as exc:
        # One article's page must not fail the feed; log the type only.
        logger.warning(
            "Full text for article %d failed: %s", article.id, type(exc).__name__
        )
        return
    if text is not None:
        repository.set_full_text(article.id, text)


def _ingest_isolated(
    url: str,
    fetch: Fetcher,
    repository: ArticleRepository,
    clock: Clock,
    feed_id: int | None = None,
    fetch_page: PageFetcher | None = None,
) -> FeedResult:
    """Ingest one feed; turn any failure into a result with a safe message."""
    safe_url = redact_url(url)
    try:
        result = ingest_feed(url, fetch, repository, clock, feed_id, fetch_page)
    except (FetchError, FeedParseError) as exc:
        logger.warning("Feed %s failed: %s", safe_url, exc)
        return FeedResult(url=safe_url, error=str(exc))
    except Exception as exc:
        # Unexpected errors may carry untrusted detail; log the type only.
        logger.error("Feed %s failed unexpectedly: %s", safe_url, type(exc).__name__)
        return FeedResult(url=safe_url, error=f"Unexpected {type(exc).__name__}")
    logger.info(
        "Feed %s: %d new, %d duplicates, %d skipped",
        safe_url,
        result.new,
        result.duplicates,
        result.skipped,
    )
    return result


def ingest_feeds(
    urls: Iterable[str],
    fetch: Fetcher,
    repository: ArticleRepository,
    clock: Clock = _now,
) -> list[FeedResult]:
    """Ingest each feed in turn; a failing feed never stops the others."""
    return [_ingest_isolated(url, fetch, repository, clock) for url in urls]


def ingest_stored_feeds(
    feeds: FeedRepository,
    fetch: Fetcher,
    repository: ArticleRepository,
    clock: Clock = _now,
    fetch_page: PageFetcher | None = None,
) -> list[FeedResult]:
    """Ingest every enabled stored feed and record the outcome per feed.

    Disabled feeds are skipped. A failing feed never stops the others; its
    safe error message is stored as ``last_error``. Article pages are fetched
    with ``fetch_page`` only for feeds with ``fetch_full_text`` enabled.
    """
    results: list[FeedResult] = []
    for feed in feeds.list_enabled():
        fetched_at = clock()
        page_fetcher = fetch_page if feed.fetch_full_text else None
        result = _ingest_isolated(
            feed.url, fetch, repository, clock, feed.id, page_fetcher
        )
        try:
            feeds.record_fetch(feed.id, fetched_at, result.error)
        except sqlite3.Error as exc:
            # Losing one status update must not stop the remaining feeds.
            logger.error(
                "Feed %s: storing fetch status failed: %s",
                result.url,
                type(exc).__name__,
            )
        results.append(result)
    return results

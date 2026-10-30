"""Turn RSS/Atom documents into :class:`NewArticle` records.

Feed content is untrusted: it is only parsed and stored, never interpreted.
"""

import io
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import feedparser
from feedparser.exceptions import ThingsNobodyCaresAboutButMe

from ai_radar.articles.models import NewArticle
from ai_radar.articles.url import normalize_url

MAX_SOURCE_LENGTH = 200
MAX_TITLE_LENGTH = 1000
MAX_CONTENT_LENGTH = 100_000


class FeedParseError(Exception):
    """A document is not a usable RSS/Atom feed; the message is safe to log."""


@dataclass(frozen=True, slots=True)
class ParsedFeed:
    source: str
    articles: list[NewArticle]
    skipped: int  # entries without a usable http(s) link


def _clean(value: Any, max_length: int) -> str:
    """Collapse whitespace and cap the length of a text field."""
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:max_length]


def _to_datetime(value: Any) -> datetime | None:
    # feedparser normalizes parsed dates to UTC struct_time values.
    if not isinstance(value, time.struct_time):
        return None
    try:
        return datetime(*value[:6], tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def _entry_date(entry: Any) -> Any:
    published = entry.get("published_parsed")
    # ``in`` avoids feedparser's deprecated updated->published key fallback.
    if published is None and "updated_parsed" in entry:
        return entry["updated_parsed"]
    return published


def _is_malformed(parsed: Any) -> bool:
    if not parsed.get("version"):
        return True
    # Benign bozo reasons, e.g. a missing or non-XML Content-Type header.
    error = parsed.get("bozo_exception")
    return bool(parsed.bozo) and not isinstance(error, ThingsNobodyCaresAboutButMe)


def _to_article(entry: Any, source: str, collected_at: datetime) -> NewArticle | None:
    url = entry.get("link")
    if not isinstance(url, str):
        return None
    url = url.strip()
    try:
        normalize_url(url)
    except ValueError:
        return None
    summary = entry.get("summary")
    content = summary[:MAX_CONTENT_LENGTH] if isinstance(summary, str) else None
    return NewArticle(
        source=source,
        url=url,
        title=_clean(entry.get("title"), MAX_TITLE_LENGTH) or url,
        content=content or None,
        published_at=_to_datetime(_entry_date(entry)),
        collected_at=collected_at,
    )


def parse_feed(content: bytes, feed_url: str, collected_at: datetime) -> ParsedFeed:
    """Parse ``content`` fetched from ``feed_url``.

    Relative entry links are resolved against ``feed_url``. Entries without a
    usable http(s) link are skipped. Raises :class:`FeedParseError` if the
    document is not a feed.
    """
    # Pass a stream, never bytes or str: feedparser treats those as a possible
    # URL or local file name and would open it.
    parsed = feedparser.parse(
        io.BytesIO(content),
        response_headers={"content-location": feed_url},
        resolve_relative_uris=True,
        sanitize_html=True,
    )
    # Feeds with some usable entries are accepted even if partly malformed.
    if not parsed.entries and _is_malformed(parsed):
        reason = type(parsed.get("bozo_exception")).__name__
        raise FeedParseError(f"Not a valid RSS/Atom feed ({reason})")

    source = _clean(parsed.feed.get("title"), MAX_SOURCE_LENGTH)
    if not source:
        source = urlsplit(feed_url).hostname or feed_url

    articles: list[NewArticle] = []
    skipped = 0
    for entry in parsed.entries:
        article = _to_article(entry, source, collected_at)
        if article is None:
            skipped += 1
        else:
            articles.append(article)
    return ParsedFeed(source=source, articles=articles, skipped=skipped)

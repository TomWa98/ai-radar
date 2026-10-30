"""Full-text extraction for articles of feeds with the opt-in (D3).

The article page is fetched through the SSRF-protected fetcher and cleaned of
navigation, ads, and other page elements with ``trafilatura``. Whenever the
full text is not freely available, the caller keeps the feed excerpt: on any
fetch error (including HTTP 401/402/403), an empty extract, or a page that
marks itself as paywalled. Paywalls and access restrictions are never bypassed.

The extracted text is untrusted data.
"""

import logging
import re
from collections.abc import Callable

import trafilatura

from ai_radar.ingest.fetch import FetchedFeed, FetchError
from ai_radar.ingest.parse import MAX_CONTENT_LENGTH

logger = logging.getLogger(__name__)

PageFetcher = Callable[[str], FetchedFeed]

# schema.org paywall markup (JSON-LD or microdata), as recommended by search
# engines for subscription content: "isAccessibleForFree": false.
_PAYWALL_MARKERS = (
    re.compile(rb"""["']isAccessibleForFree["']\s*:\s*["']?false""", re.IGNORECASE),
    re.compile(
        rb"""itemprop\s*=\s*["']?isAccessibleForFree["']?[^>]*?"""
        rb"""content\s*=\s*["']?false""",
        re.IGNORECASE,
    ),
    re.compile(
        rb"""content\s*=\s*["']?false["']?[^>]*?"""
        rb"""itemprop\s*=\s*["']?isAccessibleForFree""",
        re.IGNORECASE,
    ),
)


def is_paywalled(html: bytes) -> bool:
    """Return ``True`` if the page declares that it is not freely accessible."""
    return any(marker.search(html) for marker in _PAYWALL_MARKERS)


def extract_full_text(url: str, fetch_page: PageFetcher) -> str | None:
    """Return the cleaned article text, or ``None`` to keep the feed excerpt."""
    try:
        page = fetch_page(url)
    except FetchError as exc:
        logger.info("Full text for %s unavailable: %s", url, exc)
        return None
    if is_paywalled(page.content):
        logger.info("Full text for %s unavailable: page is paywalled", url)
        return None
    text = trafilatura.extract(page.content, url=page.url, include_comments=False)
    if not text or not text.strip():
        logger.info("Full text for %s unavailable: nothing extracted", url)
        return None
    return text.strip()[:MAX_CONTENT_LENGTH]

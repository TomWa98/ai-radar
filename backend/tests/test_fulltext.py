import logging
from collections.abc import Callable
from functools import partial

import httpx
import pytest

from ai_radar.ingest import fulltext
from ai_radar.ingest.fetch import FetchedFeed, fetch_page
from ai_radar.ingest.fulltext import extract_full_text, is_paywalled
from ai_radar.ingest.parse import MAX_CONTENT_LENGTH

PUBLIC_IP = "93.184.215.14"
URL = "https://news.example/posts/1"

ARTICLE = b"""<!doctype html><html><head><title>Big release</title></head><body>
<nav>Home | About | Login</nav>
<article><h1>Big release</h1>
<p>The new model ships today with a much larger context window and better tool use.</p>
<p>Benchmarks show strong gains on coding tasks, and pricing stays the same.</p>
</article>
<aside>Advertisement: buy now</aside>
<footer>Copyright 2026 Example Inc.</footer><script>track()</script>
</body></html>"""

EMPTY = b"<!doctype html><html><head><title>x</title></head><body></body></html>"

PAYWALL_JSON_LD = ARTICLE.replace(
    b"<head>",
    b"""<head><script type="application/ld+json">
{"@type": "NewsArticle", "isAccessibleForFree": false}</script>""",
)
PAYWALL_JSON_LD_STRING = ARTICLE.replace(
    b"<head>",
    b"""<head><script type="application/ld+json">
{"@type": "NewsArticle", "isAccessibleForFree": "False"}</script>""",
)
PAYWALL_MICRODATA = ARTICLE.replace(
    b"<head>", b'<head><meta itemprop="isAccessibleForFree" content="false">'
)
PAYWALL_MICRODATA_REVERSED = ARTICLE.replace(
    b"<head>", b'<head><meta content="false" itemprop="isAccessibleForFree">'
)
FREE_JSON_LD = ARTICLE.replace(
    b"<head>",
    b"""<head><script type="application/ld+json">
{"@type": "NewsArticle", "isAccessibleForFree": true}</script>""",
)


def resolver(table: dict[str, list[str]]) -> Callable[[str, int], list[str]]:
    def resolve(host: str, port: int) -> list[str]:
        return table.get(host, [PUBLIC_IP])

    return resolve


def page_fetcher(
    handler: Callable[[httpx.Request], httpx.Response],
    table: dict[str, list[str]] | None = None,
) -> tuple[Callable[[str], FetchedFeed], httpx.Client]:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return partial(fetch_page, client=client, resolve=resolver(table or {})), client


def serve(body: bytes, status: int = 200) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(status, content=body)


def test_extracts_article_text_without_page_chrome() -> None:
    fetch, client = page_fetcher(serve(ARTICLE))
    with client:
        text = extract_full_text(URL, fetch)

    assert text is not None
    assert "much larger context window" in text
    assert "pricing stays the same" in text
    for chrome in ("Login", "Advertisement", "Copyright", "track()"):
        assert chrome not in text


def test_page_request_headers_and_no_cookies() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/old":
            return httpx.Response(
                302, headers={"location": "/posts/1", "set-cookie": "session=abc"}
            )
        return httpx.Response(200, content=ARTICLE)

    fetch, client = page_fetcher(handler)
    with client:
        assert extract_full_text("https://news.example/old", fetch) is not None

    assert [r.url.path for r in requests] == ["/old", "/posts/1"]
    for request in requests:
        assert request.headers["accept"].startswith("text/html")
        assert request.headers["accept-encoding"] == "identity"
        assert "cookie" not in request.headers
        assert "authorization" not in request.headers


@pytest.mark.parametrize("status", [401, 402, 403, 404, 500])
def test_access_denied_or_error_falls_back(
    status: int, caplog: pytest.LogCaptureFixture
) -> None:
    fetch, client = page_fetcher(serve(ARTICLE, status))
    with client, caplog.at_level(logging.INFO):
        assert extract_full_text(URL, fetch) is None
    assert f"HTTP status {status}" in caplog.text


def test_empty_page_falls_back() -> None:
    fetch, client = page_fetcher(serve(EMPTY))
    with client:
        assert extract_full_text(URL, fetch) is None


@pytest.mark.parametrize(
    "page",
    [
        PAYWALL_JSON_LD,
        PAYWALL_JSON_LD_STRING,
        PAYWALL_MICRODATA,
        PAYWALL_MICRODATA_REVERSED,
    ],
)
def test_paywalled_page_falls_back(
    page: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    def never(*args: object, **kwargs: object) -> str:
        raise AssertionError("paywalled content must not be extracted")

    monkeypatch.setattr(fulltext.trafilatura, "extract", never)
    fetch, client = page_fetcher(serve(page))
    with client:
        assert extract_full_text(URL, fetch) is None


def test_free_page_is_not_paywalled() -> None:
    assert not is_paywalled(FREE_JSON_LD)
    assert not is_paywalled(ARTICLE)


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "::1"])
def test_private_article_url_is_never_requested(address: str) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=ARTICLE)

    fetch, client = page_fetcher(handler, {"internal.example": [address]})
    with client:
        assert extract_full_text("http://internal.example/admin", fetch) is None
    assert requests == []


def test_redirect_to_private_address_is_blocked() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://metadata.internal/"})

    fetch, client = page_fetcher(handler, {"metadata.internal": ["169.254.169.254"]})
    with client:
        assert extract_full_text(URL, fetch) is None
    assert requested == [URL]


def test_non_http_article_url_falls_back() -> None:
    fetch, client = page_fetcher(serve(ARTICLE))
    with client:
        assert extract_full_text("file:///etc/passwd", fetch) is None


def test_oversized_page_falls_back() -> None:
    big = b"<html><body><p>" + b"x" * (5 * 1024 * 1024 + 1) + b"</p></body></html>"
    fetch, client = page_fetcher(serve(big))
    with client:
        assert extract_full_text(URL, fetch) is None


def test_extracted_text_is_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fulltext.trafilatura,
        "extract",
        lambda *args, **kwargs: "y" * (MAX_CONTENT_LENGTH + 10),
    )
    fetch, client = page_fetcher(serve(ARTICLE))
    with client:
        text = extract_full_text(URL, fetch)
    assert text == "y" * MAX_CONTENT_LENGTH

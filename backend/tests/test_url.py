import pytest

from ai_radar.articles.url import normalize_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("HTTPS://Example.COM/News", "https://example.com/News"),
        ("https://example.com:443/a", "https://example.com/a"),
        ("http://example.com:80/a", "http://example.com/a"),
        ("https://example.com:8443/a", "https://example.com:8443/a"),
        ("https://example.com/a#comments", "https://example.com/a"),
        (
            "https://example.com/a?utm_source=rss&id=7&UTM_Medium=x&fbclid=abc",
            "https://example.com/a?id=7",
        ),
        ("https://example.com/a?b=2&a=1", "https://example.com/a?a=1&b=2"),
        ("https://example.com/a?utm_source=rss", "https://example.com/a"),
        ("https://[2001:DB8::1]:443/a", "https://[2001:db8::1]/a"),
        ("https://example.com/#/news/1", "https://example.com/#/news/1"),
        ("https://example.com/#!/news/1", "https://example.com/#!/news/1"),
        ("https://example.com/a?id=2&id=1", "https://example.com/a?id=2&id=1"),
        (
            "https://example.com/a?z=1&tag=b&utm_source=x&tag=a",
            "https://example.com/a?tag=b&tag=a&z=1",
        ),
    ],
)
def test_normalize_url(url: str, expected: str) -> None:
    assert normalize_url(url) == expected


def test_path_case_and_trailing_slash_are_preserved() -> None:
    assert normalize_url("https://example.com/News/") == "https://example.com/News/"
    assert normalize_url("https://example.com/News") != normalize_url(
        "https://example.com/news"
    )


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("https://example.com/#/news/1", "https://example.com/#/news/2"),
        ("https://example.com/#!/news/1", "https://example.com/#!/news/2"),
        ("https://example.com/a?id=1&id=2", "https://example.com/a?id=2&id=1"),
    ],
)
def test_semantically_different_urls_stay_distinct(first: str, second: str) -> None:
    assert normalize_url(first) != normalize_url(second)


def test_non_routing_fragments_are_removed() -> None:
    assert normalize_url("https://example.com/a#section-2") == "https://example.com/a"


@pytest.mark.parametrize(
    "url",
    [
        "https://user:secret@example.com/a",
        "https://user@example.com/a",
        "https://@example.com/a",
    ],
)
def test_rejects_urls_with_credentials(url: str) -> None:
    with pytest.raises(ValueError, match="credentials"):
        normalize_url(url)


def test_http_and_https_are_distinct() -> None:
    assert normalize_url("http://example.com/a") != normalize_url("https://example.com/a")


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "ftp://example.com/a",
        "/relative",
        "",
    ],
)
def test_rejects_non_http_urls(url: str) -> None:
    with pytest.raises(ValueError):
        normalize_url(url)

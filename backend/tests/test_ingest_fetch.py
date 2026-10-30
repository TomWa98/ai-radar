import socket
from collections.abc import Callable

import httpx
import pytest

from ai_radar.ingest.fetch import (
    FetchError,
    UnsafeURLError,
    check_url,
    create_client,
    fetch_feed,
    resolve_host,
)

PUBLIC_IP = "93.184.215.14"
FEED = b"<rss version='2.0'><channel><title>T</title></channel></rss>"


def resolver(table: dict[str, list[str]]) -> Callable[[str, int], list[str]]:
    def resolve(host: str, port: int) -> list[str]:
        return table.get(host, [PUBLIC_IP])

    return resolve


def client_for(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def test_fetch_returns_body() -> None:
    with client_for(lambda request: httpx.Response(200, content=FEED)) as client:
        assert (
            fetch_feed("https://example.com/feed", client, resolve=resolver({})) == FEED
        )


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/feed",
        "file:///etc/passwd",
        "https://user:secret@example.com/feed",
        "https:///feed",
        "https://example.com:99999/feed",
    ],
)
def test_check_url_rejects_unsupported_urls(url: str) -> None:
    with pytest.raises(UnsafeURLError):
        check_url(url, resolver({}))


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.5",
        "172.16.0.1",
        "192.168.1.10",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "224.0.0.1",
        "::1",
        "fe80::1%en0",
        "fd00::1",
        "::ffff:127.0.0.1",
        "2002:7f00:1::",  # 6to4 for 127.0.0.1
        "2001:0:4136:e378:8000:63bf:3fff:fdd2",  # Teredo
    ],
)
def test_check_url_rejects_non_public_addresses(address: str) -> None:
    with pytest.raises(UnsafeURLError):
        check_url(
            "https://internal.example/feed", resolver({"internal.example": [address]})
        )


def test_check_url_rejects_if_any_address_is_private() -> None:
    table = {"mixed.example": [PUBLIC_IP, "10.0.0.1"]}
    with pytest.raises(UnsafeURLError):
        check_url("http://mixed.example/", resolver(table))


def test_check_url_accepts_public_host() -> None:
    check_url(
        "https://example.com/feed",
        resolver({"example.com": [PUBLIC_IP, "2606:4700::1"]}),
    )


def test_unsafe_url_is_never_requested() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=FEED)

    with client_for(handler) as client, pytest.raises(UnsafeURLError):
        fetch_feed(
            "http://localhost/feed",
            client,
            resolve=resolver({"localhost": ["127.0.0.1"]}),
        )
    assert requests == []


def test_redirect_to_public_target_is_followed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new"})
        return httpx.Response(200, content=FEED)

    with client_for(handler) as client:
        assert (
            fetch_feed("https://example.com/old", client, resolve=resolver({})) == FEED
        )


def test_redirect_to_private_target_is_blocked() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(
            302, headers={"location": "http://metadata.internal/latest"}
        )

    table = {"metadata.internal": ["169.254.169.254"]}
    with client_for(handler) as client, pytest.raises(UnsafeURLError):
        fetch_feed("https://example.com/feed", client, resolve=resolver(table))
    assert requested == ["https://example.com/feed"]


def test_redirect_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/loop"})

    with client_for(handler) as client, pytest.raises(FetchError, match="redirects"):
        fetch_feed(
            "https://example.com/feed", client, resolve=resolver({}), max_redirects=3
        )


def test_http_error_status_fails() -> None:
    with client_for(lambda request: httpx.Response(404)) as client:
        with pytest.raises(FetchError, match="404"):
            fetch_feed("https://example.com/feed", client, resolve=resolver({}))


def test_timeout_becomes_fetch_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with client_for(handler) as client, pytest.raises(FetchError, match="ReadTimeout"):
        fetch_feed("https://example.com/feed", client, resolve=resolver({}))


def test_declared_oversize_response_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-length": "1000"}, content=b"x" * 1000
        )

    with client_for(handler) as client, pytest.raises(FetchError, match="larger"):
        fetch_feed(
            "https://example.com/feed", client, resolve=resolver({}), max_bytes=100
        )


def test_streamed_oversize_response_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # A generator body has no Content-Length header.
        return httpx.Response(200, content=iter([b"x" * 60, b"x" * 60]))

    with client_for(handler) as client, pytest.raises(FetchError, match="larger"):
        fetch_feed(
            "https://example.com/feed", client, resolve=resolver({}), max_bytes=100
        )


def test_no_cookies_are_sent() -> None:
    cookie_headers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        cookie_headers.append(request.headers.get("cookie"))
        if request.url.path == "/old":
            return httpx.Response(
                302, headers={"location": "/new", "set-cookie": "s=1; Path=/"}
            )
        return httpx.Response(200, content=FEED)

    with client_for(handler) as client:
        fetch_feed("https://example.com/old", client, resolve=resolver({}))
    assert cookie_headers == [None, None]


def test_create_client_settings() -> None:
    with create_client(timeout=3.0) as client:
        assert client.timeout.read == 3.0
        assert client.follow_redirects is False
        assert client.trust_env is False


def test_resolve_host_failure_is_fetch_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise socket.gaierror("no such host")

    monkeypatch.setattr(socket, "getaddrinfo", fail)
    with pytest.raises(FetchError, match="resolve"):
        resolve_host("nonexistent.invalid", 443)

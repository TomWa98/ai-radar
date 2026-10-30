"""Fetch feed documents over HTTP with SSRF protection and resource limits.

Every request target, including each redirect target, must be an http(s) URL
without credentials whose host resolves only to public addresses. Redirects are
followed manually so that each hop is checked before it is requested.

Known residual risk (DNS rebinding): httpx resolves the host again when it
connects. A host whose DNS answer changes between the check and the connection
can still reach an internal address. See ``docs/architecture.md``.
"""

import ipaddress
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

USER_AGENT = "AI-Radar/0.1 (+self-hosted feed reader)"
TIMEOUT = 10.0  # seconds per connect/read/write/pool operation
TOTAL_TIMEOUT = 30.0  # seconds for one feed, including redirects
DNS_TIMEOUT = 10.0  # seconds per host lookup, also bounded by TOTAL_TIMEOUT
MAX_BYTES = 5 * 1024 * 1024  # after decompression
MAX_REDIRECTS = 5

_ACCEPT = (
    "application/rss+xml, application/atom+xml, application/xml;q=0.9, "
    "text/xml;q=0.9, */*;q=0.1"
)

# Ask for an uncompressed body. Servers may compress anyway; the size limit is
# applied to the decompressed data either way.
_REQUEST_HEADERS = {"Accept-Encoding": "identity"}

# NAT64 well-known prefix (RFC 6052): the gateway may reach any IPv4 address,
# including private ones, so these addresses are never treated as public.
_NAT64 = ipaddress.ip_network("64:ff9b::/96")

Resolver = Callable[[str, int], list[str]]


@dataclass(frozen=True, slots=True)
class FetchedFeed:
    content: bytes
    url: str  # final URL after redirects; base for relative links


class FetchError(Exception):
    """A feed could not be fetched; the message is safe to log."""


class UnsafeURLError(FetchError):
    """A URL is not allowed as a fetch target."""


def resolve_host(host: str, port: int) -> list[str]:
    """Return all IP addresses ``host`` resolves to."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as exc:
        raise FetchError(f"Cannot resolve host {host!r}") from exc
    return [str(info[4][0]) for info in infos]


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])  # drop IPv6 zone id
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.teredo is not None or ip in _NAT64:
            return False
        # IPv6 forms that embed an IPv4 address are judged by that address.
        embedded = ip.ipv4_mapped or ip.sixtofour
        if embedded is not None:
            ip = embedded
    return ip.is_global and not ip.is_multicast


def check_url(url: str, resolve: Resolver = resolve_host) -> None:
    """Raise :class:`UnsafeURLError` unless ``url`` is a permitted fetch target."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise UnsafeURLError("Invalid URL") from exc
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise UnsafeURLError(f"Unsupported URL scheme: {parts.scheme!r}")
    if "@" in parts.netloc:
        raise UnsafeURLError("URLs with embedded credentials are not allowed")
    host = parts.hostname
    if not host:
        raise UnsafeURLError("URL has no host")
    if port is None:
        port = 443 if scheme == "https" else 80

    addresses = resolve(host, port)
    if not addresses:
        raise FetchError(f"Cannot resolve host {host!r}")
    if not all(_is_public(address) for address in addresses):
        raise UnsafeURLError(f"Host {host!r} resolves to a non-public address")


def _resolve_with_timeout(resolve: Resolver, timeout: float) -> Resolver:
    """Wrap ``resolve`` so that one lookup fails after ``timeout`` seconds.

    A blocking lookup cannot be cancelled; it finishes in a daemon thread whose
    result is discarded.
    """

    def bounded(host: str, port: int) -> list[str]:
        if timeout <= 0:
            raise FetchError("Feed download took too long")
        outcome: list[list[str] | BaseException] = []

        def run() -> None:
            try:
                outcome.append(resolve(host, port))
            except BaseException as exc:
                outcome.append(exc)

        thread = threading.Thread(target=run, name="resolve-host", daemon=True)
        thread.start()
        thread.join(timeout)
        if not outcome:
            raise FetchError(f"Resolving host {host!r} took too long")
        result = outcome[0]
        if isinstance(result, BaseException):
            raise result
        return result

    return bounded


def create_client(timeout: float = TIMEOUT) -> httpx.Client:
    """Create an HTTP client for :func:`fetch_feed`.

    Environment proxies and ``.netrc`` credentials are ignored
    (``trust_env=False``) so requests go directly to the checked host.
    """
    return httpx.Client(
        timeout=httpx.Timeout(timeout),
        follow_redirects=False,
        trust_env=False,
        headers={"User-Agent": USER_AGENT, "Accept": _ACCEPT},
    )


def _read_limited(response: httpx.Response, max_bytes: int, deadline: float) -> bytes:
    declared = response.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > max_bytes:
        raise FetchError(f"Response larger than {max_bytes} bytes")
    chunks: list[bytes] = []
    size = 0
    # iter_bytes() yields decompressed data, so the limit also bounds gzip bombs.
    for chunk in response.iter_bytes():
        size += len(chunk)
        if size > max_bytes:
            raise FetchError(f"Response larger than {max_bytes} bytes")
        if time.monotonic() > deadline:
            raise FetchError("Feed download took too long")
        chunks.append(chunk)
    return b"".join(chunks)


def fetch_feed(
    url: str,
    client: httpx.Client,
    *,
    resolve: Resolver = resolve_host,
    max_bytes: int = MAX_BYTES,
    max_redirects: int = MAX_REDIRECTS,
    total_timeout: float = TOTAL_TIMEOUT,
) -> FetchedFeed:
    """Return the body and final URL; raise :class:`FetchError` on any failure."""
    deadline = time.monotonic() + total_timeout
    for _ in range(max_redirects + 1):
        remaining = deadline - time.monotonic()
        check_url(url, _resolve_with_timeout(resolve, min(DNS_TIMEOUT, remaining)))
        if time.monotonic() > deadline:
            raise FetchError("Feed download took too long")
        # No cookies are carried over between requests or hops.
        client.cookies.clear()
        try:
            with client.stream("GET", url, headers=_REQUEST_HEADERS) as response:
                if response.is_redirect:
                    url = str(response.url.join(response.headers["location"]))
                    continue
                if response.status_code != httpx.codes.OK:
                    raise FetchError(f"HTTP status {response.status_code}")
                return FetchedFeed(_read_limited(response, max_bytes, deadline), url)
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            raise FetchError(f"Request failed: {type(exc).__name__}") from exc
    raise FetchError(f"More than {max_redirects} redirects")

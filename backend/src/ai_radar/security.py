"""Request checks for the unauthenticated, localhost-only API (D9)."""

from urllib.parse import urlsplit

from fastapi import HTTPException, Request, status

# Host names the API answers to; also the only accepted request origins.
LOCAL_HOSTS = ("127.0.0.1", "localhost")


def require_local_origin(request: Request) -> None:
    """Reject browser requests sent from a foreign website (CSRF).

    Browsers send ``Origin`` with every cross-site POST, so a request whose
    ``Origin`` is not a local address is refused. Requests without ``Origin``
    (e.g. ``curl``) are allowed; they cannot come from another website.
    """
    origin = request.headers.get("origin")
    if origin is None:
        return
    try:
        parts = urlsplit(origin)
    except ValueError:  # e.g. a malformed IPv6 literal
        allowed = False
    else:
        allowed = parts.scheme in ("http", "https") and parts.hostname in LOCAL_HOSTS
    if not allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-origin request refused")

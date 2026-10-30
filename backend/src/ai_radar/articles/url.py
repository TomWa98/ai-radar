"""Conservative URL normalization used for duplicate detection."""

from urllib.parse import urlsplit, urlunsplit

_DEFAULT_PORTS = {"http": 80, "https": 443}
_TRACKING_PARAMS = frozenset(
    {"fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid"}
)
_TRACKING_PREFIXES = ("utm_",)
# Fragments used for client-side routing identify different content.
_ROUTING_FRAGMENT_PREFIXES = ("/", "!/")


def _is_tracking_param(name: str) -> bool:
    name = name.lower()
    return name in _TRACKING_PARAMS or name.startswith(_TRACKING_PREFIXES)


def _param_name(param: str) -> str:
    return param.partition("=")[0]


def normalize_url(url: str) -> str:
    """Return a canonical form of an http(s) URL.

    Lowercases scheme and host and drops default ports, known tracking
    parameters, and fragments other than routing fragments (``#/``, ``#!/``).
    Query parameters are sorted by name; repeated parameters keep their
    relative order. Path and parameter values are kept verbatim.

    Raises ``ValueError`` for anything that is not an absolute http(s) URL and
    for URLs with embedded credentials.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        raise ValueError(f"Unsupported URL scheme: {parts.scheme!r}")
    if "@" in parts.netloc:
        raise ValueError("URLs with embedded credentials are not allowed")
    host = parts.hostname  # already lowercased by urlsplit
    if not host:
        raise ValueError("URL has no host")

    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    port = parts.port
    netloc = host if port in (None, _DEFAULT_PORTS[scheme]) else f"{host}:{port}"

    params = [
        param
        for param in parts.query.split("&")
        if param and not _is_tracking_param(_param_name(param))
    ]
    # sorted() is stable: repeated parameters keep their original order.
    query = "&".join(sorted(params, key=_param_name))

    fragment = parts.fragment
    if not fragment.startswith(_ROUTING_FRAGMENT_PREFIXES):
        fragment = ""

    return urlunsplit((scheme, netloc, parts.path, query, fragment))

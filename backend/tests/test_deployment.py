"""Guards for the security rules of the Compose setup (D11).

Docker is not available in these tests, so they check the configuration files.
The behavior of a running installation is covered by docs/deployment.md.
"""

import re
from pathlib import Path

import pytest

from ai_radar.main import ALLOWED_HOSTS
from ai_radar.security import LOCAL_HOSTS

REPO_ROOT = Path(__file__).resolve().parents[2]
PINNED_IMAGE = re.compile(r"[a-z]+:\d+\.\d+\.\d+-[a-z]+@sha256:[0-9a-f]{64}")


def read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def code_lines(text: str) -> str:
    """The text without comments, so explanations cannot satisfy a check."""
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def nginx_conf() -> str:
    return code_lines(read("frontend/nginx.conf"))


def compose_service(name: str) -> str:
    """The lines of one service in compose.yaml."""
    match = re.search(
        rf"^  {name}:\n((?:(?:    .*)?\n)+)", code_lines(read("compose.yaml")), re.M
    )
    assert match, f"service {name} not found"
    return match.group(1)


def test_backend_accepts_only_local_hosts() -> None:
    assert ALLOWED_HOSTS == list(LOCAL_HOSTS)
    assert "*" not in ALLOWED_HOSTS


def test_nginx_accepts_exactly_the_hosts_of_the_backend() -> None:
    names = re.findall(r"server_name\s+([^;_][^;]*);", nginx_conf())

    assert len(names) == 1
    assert set(names[0].split()) == set(LOCAL_HOSTS)


def test_nginx_rejects_other_hosts_without_forwarding() -> None:
    match = re.search(r"server\s*\{([^{}]*default_server[^{}]*)\}", nginx_conf())

    assert match, "no default_server block"
    assert "return 444;" in match.group(1)
    assert "proxy_pass" not in match.group(1)


def test_nginx_forwards_the_original_host() -> None:
    conf = nginx_conf()

    assert conf.count("proxy_pass") == 2
    assert re.findall(r"proxy_set_header\s+Host\s+([^;]+);", conf) == ["$host", "$host"]
    assert "proxy_set_header Origin" not in conf


def test_nginx_has_no_spa_fallback() -> None:
    assert "/index.html" not in nginx_conf()


def test_only_the_frontend_publishes_a_port_on_loopback() -> None:
    assert "ports:" not in compose_service("backend")
    published = re.findall(r'-\s*"([^"]+:\d+:\d+)"', compose_service("frontend"))

    assert published == ["127.0.0.1:8080:80"]


def test_database_is_on_the_named_volume() -> None:
    backend = compose_service("backend")

    assert "AI_RADAR_DB: /data/ai-radar.db" in backend
    assert "- ai-radar-data:/data" in backend
    assert re.search(r"^volumes:\n  ai-radar-data:", read("compose.yaml"), re.M)


@pytest.mark.parametrize("context", ["backend", "frontend"])
def test_secrets_stay_out_of_the_build_context(context: str) -> None:
    ignored = read(f"{context}/.dockerignore").splitlines()

    assert ".env" in ignored
    assert ".env.*" in ignored


@pytest.mark.parametrize("dockerfile", ["backend/Dockerfile", "frontend/Dockerfile"])
def test_base_images_are_pinned_to_version_and_digest(dockerfile: str) -> None:
    images = re.findall(r"^FROM\s+(\S+)", read(dockerfile), re.M)

    assert images
    for image in images:
        assert PINNED_IMAGE.fullmatch(image), image

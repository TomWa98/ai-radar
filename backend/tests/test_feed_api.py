import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_radar.feeds.repository import FeedRepository
from ai_radar.main import DB_PATH_ENV, app


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "api.db"
    monkeypatch.setenv(DB_PATH_ENV, str(path))
    return path


@pytest.fixture
def client(db_path: Path) -> Iterator[TestClient]:
    # The context manager runs the lifespan (schema setup).
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client


def create(client: TestClient, **fields: object) -> dict[str, object]:
    response = client.post(
        "/api/feeds", json={"url": "https://example.com/rss", **fields}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_startup_creates_database(client: TestClient, db_path: Path) -> None:
    assert db_path.exists()
    assert client.get("/api/feeds").json() == []


def test_create_returns_feed_with_defaults(client: TestClient) -> None:
    feed = create(client, url="  https://example.com/rss  ")

    assert feed["url"] == "https://example.com/rss"
    assert feed["name"] is None
    assert feed["enabled"] is True
    assert feed["fetch_full_text"] is False
    assert isinstance(feed["id"], int)
    assert set(feed) == {
        "id",
        "url",
        "name",
        "enabled",
        "fetch_full_text",
        "created_at",
        "updated_at",
    }


def test_create_trims_name_and_treats_blank_as_missing(client: TestClient) -> None:
    assert create(client, name="  Example  ")["name"] == "Example"
    assert create(client, url="https://b.example/rss", name="   ")["name"] is None


def test_list_returns_created_feeds(client: TestClient) -> None:
    first = create(client, name="A", enabled=False)
    second = create(client, url="https://b.example/atom", fetch_full_text=True)

    assert client.get("/api/feeds").json() == [first, second]


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/rss",
        "javascript:alert(1)",
        "https://user:secret@example.com/rss",
        "example.com/rss",
        "",
        "https://example.com/" + "a" * 2048,
    ],
)
def test_create_rejects_invalid_url(client: TestClient, url: str) -> None:
    response = client.post("/api/feeds", json={"url": url})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "url"]
    assert client.get("/api/feeds").json() == []


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"url": None},
        {"url": "https://example.com/rss", "enabled": "maybe"},
        {"url": "https://example.com/rss", "name": "x" * 201},
        {"url": "https://example.com/rss", "id": 7},
    ],
)
def test_create_rejects_invalid_body(client: TestClient, body: object) -> None:
    assert client.post("/api/feeds", json=body).status_code == 422


def test_invalid_url_message_is_readable(client: TestClient) -> None:
    response = client.post("/api/feeds", json={"url": "ftp://example.com/rss"})

    assert "Unsupported URL scheme" in response.json()["detail"][0]["msg"]


def test_create_duplicate_returns_409(client: TestClient) -> None:
    existing = create(client, name="Original")

    response = client.post(
        "/api/feeds", json={"url": "HTTPS://example.com:443/rss#x", "name": "Copy"}
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "A feed with this URL already exists"}
    assert client.get("/api/feeds").json() == [existing]


def test_patch_changes_only_given_fields(client: TestClient) -> None:
    feed = create(client, name="Old")

    response = client.patch(f"/api/feeds/{feed['id']}", json={"enabled": False})

    assert response.status_code == 200
    updated = response.json()
    assert updated["enabled"] is False
    assert (updated["url"], updated["name"]) == (feed["url"], "Old")
    assert updated["created_at"] == feed["created_at"]


def test_patch_can_change_url_and_clear_name(client: TestClient) -> None:
    feed = create(client, name="Old")

    response = client.patch(
        f"/api/feeds/{feed['id']}",
        json={"url": "https://example.com/new", "name": None, "fetch_full_text": True},
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["url"] == "https://example.com/new"
    assert updated["name"] is None
    assert updated["fetch_full_text"] is True
    assert client.get("/api/feeds").json() == [updated]


@pytest.mark.parametrize(
    "body",
    [
        {"url": "ftp://example.com/rss"},
        {"url": None},
        {"enabled": None},
        {"fetch_full_text": None},
        {"unknown": 1},
    ],
)
def test_patch_rejects_invalid_body(client: TestClient, body: object) -> None:
    feed = create(client)

    response = client.patch(f"/api/feeds/{feed['id']}", json=body)

    assert response.status_code == 422
    assert client.get("/api/feeds").json() == [feed]


def test_patch_to_duplicate_url_returns_409(client: TestClient) -> None:
    first = create(client)
    second = create(client, url="https://b.example/rss")

    response = client.patch(
        f"/api/feeds/{second['id']}", json={"url": "https://EXAMPLE.com/rss"}
    )

    assert response.status_code == 409
    assert client.get("/api/feeds").json() == [first, second]


def test_delete_removes_feed(client: TestClient) -> None:
    feed = create(client)

    response = client.delete(f"/api/feeds/{feed['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert client.get("/api/feeds").json() == []


@pytest.mark.parametrize("method", ["patch", "delete"])
def test_unknown_id_returns_404(client: TestClient, method: str) -> None:
    kwargs = {"json": {"enabled": False}} if method == "patch" else {}

    response = client.request(method.upper(), "/api/feeds/999", **kwargs)

    assert response.status_code == 404
    assert response.json() == {"detail": "Feed not found"}


@pytest.mark.parametrize("feed_id", ["0", "-1", "abc", str(2**63)])
def test_out_of_range_id_returns_422(client: TestClient, feed_id: str) -> None:
    assert client.delete(f"/api/feeds/{feed_id}").status_code == 422


def test_internal_errors_are_not_exposed(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(self: FeedRepository) -> None:
        raise sqlite3.OperationalError(f"disk I/O error at {db_path}")

    monkeypatch.setattr(FeedRepository, "list_all", broken)
    with TestClient(
        app, base_url="http://127.0.0.1", raise_server_exceptions=False
    ) as client:
        response = client.get("/api/feeds")

    assert response.status_code == 500
    assert response.text == "Internal Server Error"


@pytest.mark.parametrize("host", ["localhost:8000", "127.0.0.1:5173"])
def test_local_hosts_are_accepted(client: TestClient, host: str) -> None:
    assert client.get("/api/feeds", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize("host", ["attacker.example", "192.168.1.10:8000", ""])
def test_foreign_host_is_rejected(client: TestClient, host: str) -> None:
    # DNS rebinding: a foreign site resolving to 127.0.0.1 sends its own Host.
    response = client.post(
        "/api/feeds",
        json={"url": "https://example.com/rss"},
        headers={"Host": host},
    )

    assert response.status_code == 400
    assert client.get("/api/feeds").json() == []

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_radar.db import open_database
from ai_radar.feeds.models import NewFeed
from ai_radar.feeds.repository import FeedRepository
from ai_radar.ingest.fetch import FetchedFeed, FetchError
from ai_radar.ingest.scheduler import IngestionRunner, ingest_stored_feeds_once
from ai_radar.main import DB_PATH_ENV, app

FEED = b"""<rss version="2.0"><channel><title>Feed</title>
  <item><title>One</title><link>https://example.com/1</link></item>
</channel></rss>"""


class FakeFetcher:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.release = threading.Event()
        self.release.set()  # set: fetches return immediately

    def __call__(self, url: str) -> FetchedFeed:
        self.calls.append(url)
        self.release.wait(5)
        if "down" in url:
            raise FetchError("HTTP status 503")
        return FetchedFeed(FEED, url)


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "api.db"
    monkeypatch.setenv(DB_PATH_ENV, str(path))
    return path


@pytest.fixture
def fetch(monkeypatch: pytest.MonkeyPatch) -> FakeFetcher:
    fake = FakeFetcher()
    monkeypatch.setattr(
        "ai_radar.main.ingest_stored_feeds_once",
        lambda db_path: ingest_stored_feeds_once(db_path, fake),
    )
    return fake


@pytest.fixture
def client(db_path: Path, fetch: FakeFetcher) -> Iterator[TestClient]:
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client


def runner() -> IngestionRunner:
    return app.state.ingestion


def add_feeds(db_path: Path, *urls: str) -> None:
    with open_database(db_path) as conn:
        feeds = FeedRepository(conn)
        for url in urls:
            feeds.add(NewFeed(url=url))


def test_status_before_any_refresh(client: TestClient) -> None:
    assert client.get("/api/refresh").json() == {
        "running": False,
        "last_started_at": None,
        "last_finished_at": None,
    }


def test_refresh_fetches_stored_feeds(
    client: TestClient, db_path: Path, fetch: FakeFetcher
) -> None:
    add_feeds(db_path, "https://a.example/rss", "https://down.example/rss")

    response = client.post("/api/refresh")

    assert response.status_code == 202
    assert response.json() == {"status": "started"}
    assert runner().wait_until_idle(5)
    assert fetch.calls == ["https://a.example/rss", "https://down.example/rss"]
    with open_database(db_path) as conn:
        stored = FeedRepository(conn).list_all()
    assert stored[0].last_success_at is not None
    assert stored[1].last_error == "HTTP status 503"

    status = client.get("/api/refresh").json()
    assert status["running"] is False
    assert status["last_started_at"] is not None
    assert status["last_finished_at"] is not None
    assert status["last_finished_at"] >= status["last_started_at"]


def test_refresh_returns_before_fetch_finishes_and_rejects_overlap(
    client: TestClient, db_path: Path, fetch: FakeFetcher
) -> None:
    add_feeds(db_path, "https://a.example/rss")
    fetch.release.clear()  # block the fetch until the test is done
    try:
        assert client.post("/api/refresh").status_code == 202
        status = client.get("/api/refresh").json()
        assert status["running"] is True
        assert status["last_finished_at"] is None

        second = client.post("/api/refresh")
        assert second.status_code == 409
        assert second.json() == {"detail": "A refresh is already running"}
    finally:
        fetch.release.set()
    assert runner().wait_until_idle(5)
    assert fetch.calls == ["https://a.example/rss"]  # only one pass ran


def test_refresh_rejected_while_scheduled_pass_runs(client: TestClient) -> None:
    started = threading.Event()
    release = threading.Event()

    def slow() -> None:
        started.set()
        release.wait(5)

    blocked = IngestionRunner(slow)
    app.state.ingestion = blocked  # replaced for this test only
    scheduled = threading.Thread(target=blocked.try_run)  # as the scheduler does
    scheduled.start()
    try:
        assert started.wait(5)
        assert client.post("/api/refresh").status_code == 409
        assert client.get("/api/refresh").json()["running"] is True
    finally:
        release.set()
        scheduled.join()


def test_refresh_requires_local_host(client: TestClient) -> None:
    response = client.post("/api/refresh", headers={"Host": "attacker.example"})

    assert response.status_code == 400
    assert runner().status().last_started_at is None


@pytest.mark.parametrize(
    "origin",
    ["https://attacker.example", "http://192.168.1.10:8000", "null", "http://[::1"],
)
def test_cross_site_refresh_is_refused(client: TestClient, origin: str) -> None:
    # What an HTML form on a foreign website would send.
    response = client.post(
        "/api/refresh",
        headers={
            "Origin": origin,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Cross-origin request refused"}
    assert runner().status().last_started_at is None


@pytest.mark.parametrize(
    "origin", ["http://127.0.0.1:8000", "http://localhost:5173", None]
)
def test_local_or_missing_origin_may_refresh(
    client: TestClient, origin: str | None
) -> None:
    headers = {"Origin": origin} if origin else {}

    assert client.post("/api/refresh", headers=headers).status_code == 202
    assert runner().wait_until_idle(5)

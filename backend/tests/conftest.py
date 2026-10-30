import socket

import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test that tries a real DNS lookup or network connection."""

    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("Real network access in tests is not allowed")

    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture(autouse=True)
def no_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable the background feed scheduler unless a test enables it."""
    monkeypatch.setenv("AI_RADAR_FETCH_INTERVAL_MINUTES", "0")

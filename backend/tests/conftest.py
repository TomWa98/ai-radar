import os
import socket
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from ai_radar import config


@pytest.fixture(autouse=True)
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep the developer's real configuration and API key out of every test.

    Without this, a local ``.env`` or shell setting could select the paid
    OpenAI analyzer during a test. ``no_network`` is the second line of defense.
    """
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "no-such-env-file")
    with patch.dict(os.environ):  # also undoes what load_env_file adds
        for name in list(os.environ):
            if name.startswith(("AI_RADAR_", "OPENAI_")):
                del os.environ[name]
        yield


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test that tries a real DNS lookup or network connection."""

    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("Real network access in tests is not allowed")

    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)


@pytest.fixture(autouse=True)
def no_scheduler(isolated_config: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable the background feed scheduler unless a test enables it."""
    monkeypatch.setenv("AI_RADAR_FETCH_INTERVAL_MINUTES", "0")

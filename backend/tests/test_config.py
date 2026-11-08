import os
from pathlib import Path

import httpx
import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient

from ai_radar import config
from ai_radar.analysis import openai, pipeline
from ai_radar.analysis.pipeline import AnalysisSettings
from ai_radar.config import load_env_file
from ai_radar.main import DB_PATH_ENV, FETCH_INTERVAL_ENV, app

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_FILE = REPO_ROOT / ".env.example"
# Read at import time, before the fixtures replace it for each test.
REAL_ENV_FILE = config.ENV_FILE

NAME = "AI_RADAR_TEST_VALUE"


def write_env(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "test.env"
    path.write_text(content, encoding="utf-8")
    return path


def use_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: str) -> None:
    monkeypatch.setattr(config, "ENV_FILE", write_env(tmp_path, content))


# --- Loading ----------------------------------------------------------------


def test_loads_values_from_file(tmp_path: Path) -> None:
    assert load_env_file(write_env(tmp_path, f"{NAME}=from-file\n")) is True
    assert os.environ[NAME] == "from-file"


@pytest.mark.parametrize("existing", ["from-shell", ""])
def test_existing_variable_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, existing: str
) -> None:
    monkeypatch.setenv(NAME, existing)

    load_env_file(write_env(tmp_path, f"{NAME}=from-file\n"))

    assert os.environ[NAME] == existing


def test_missing_file_is_ignored(tmp_path: Path) -> None:
    before = dict(os.environ)

    assert load_env_file(tmp_path / "missing.env") is False

    assert dict(os.environ) == before


def test_dollar_sign_stays_literal(tmp_path: Path) -> None:
    load_env_file(write_env(tmp_path, f"{NAME}=abc${{HOME}}def\n"))
    assert os.environ[NAME] == "abc${HOME}def"


def test_default_file_is_in_repository_root() -> None:
    assert REAL_ENV_FILE == REPO_ROOT / ".env"


# --- Application startup ----------------------------------------------------


def test_startup_uses_values_from_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "from-file.db"
    use_env_file(tmp_path, monkeypatch, f"{DB_PATH_ENV}={db}\n")

    with TestClient(app, base_url="http://127.0.0.1"):
        assert app.state.db_path == db


def test_startup_prefers_existing_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from_shell = tmp_path / "from-shell.db"
    monkeypatch.setenv(DB_PATH_ENV, str(from_shell))
    use_env_file(tmp_path, monkeypatch, f"{DB_PATH_ENV}={tmp_path / 'file.db'}\n")

    with TestClient(app, base_url="http://127.0.0.1"):
        assert app.state.db_path == from_shell


def test_env_file_is_loaded_before_analysis_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(DB_PATH_ENV, str(tmp_path / "api.db"))
    use_env_file(tmp_path, monkeypatch, "AI_RADAR_ANALYZER=gpt\n")

    with pytest.raises(ValueError, match="Unknown analyzer"):
        with TestClient(app, base_url="http://127.0.0.1"):
            pass


# --- Tests cannot reach OpenAI ----------------------------------------------


def test_tests_do_not_see_the_real_configuration() -> None:
    assert config.ENV_FILE != REAL_ENV_FILE
    assert not [
        name for name in os.environ if name.startswith(("AI_RADAR_ANALYZER", "OPENAI_"))
    ]


def test_settings_in_tests_select_the_fake_analyzer() -> None:
    assert AnalysisSettings.from_env(os.environ).analyzer == "fake"


def test_real_openai_request_is_blocked() -> None:
    with pytest.raises(AssertionError, match="Real network access"):
        httpx.post(f"{openai.BASE_URL}/chat/completions", timeout=1)


# --- .env.example -----------------------------------------------------------


def example_values() -> dict[str, str | None]:
    return dict(dotenv_values(EXAMPLE_FILE, interpolate=False))


def test_example_lists_exactly_the_variables_the_code_reads() -> None:
    assert set(example_values()) == {
        DB_PATH_ENV,
        FETCH_INTERVAL_ENV,
        pipeline.ANALYZER_ENV,
        pipeline.MAX_ATTEMPTS_ENV,
        pipeline.CONCURRENCY_ENV,
        openai.API_KEY_ENV,
        openai.MODEL_ENV,
        openai.INPUT_PRICE_ENV,
        openai.OUTPUT_PRICE_ENV,
        openai.BUDGET_ENV,
    }


def test_example_is_safe_and_keeps_the_defaults() -> None:
    values = example_values()

    assert values[openai.API_KEY_ENV] == ""
    assert values[openai.BUDGET_ENV] == "0"
    assert values[DB_PATH_ENV] == "ai-radar.db"
    assert values[FETCH_INTERVAL_ENV] == "15"
    assert AnalysisSettings.from_env(
        {key: value or "" for key, value in values.items()}
    ) == AnalysisSettings("fake", 3, 2)

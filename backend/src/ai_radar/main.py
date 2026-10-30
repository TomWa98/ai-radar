"""FastAPI application entry point.

Configuration: ``AI_RADAR_DB`` is the SQLite database file (default
``ai-radar.db`` in the working directory).

The API has no authentication and is meant for ``127.0.0.1`` only (D9).
Requests for any other ``Host`` are rejected, so a website using DNS rebinding
cannot reach the API through the user's browser.
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from ai_radar.db import open_database
from ai_radar.feeds.api import router as feeds_router

DB_PATH_ENV = "AI_RADAR_DB"
DEFAULT_DB_PATH = "ai-radar.db"
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create or migrate the database schema once at startup."""
    db_path = Path(os.environ.get(DB_PATH_ENV, DEFAULT_DB_PATH))
    with open_database(db_path):
        pass
    app.state.db_path = db_path
    yield


app = FastAPI(title="AI Radar", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
app.include_router(feeds_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check: confirms the API process is running."""
    return {"status": "ok"}

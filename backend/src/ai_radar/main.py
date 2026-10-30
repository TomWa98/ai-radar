"""FastAPI application entry point.

Configuration (environment variables):

* ``AI_RADAR_DB``: SQLite database file (default ``ai-radar.db`` in the
  working directory).
* ``AI_RADAR_FETCH_INTERVAL_MINUTES``: how often the stored feeds are fetched
  (default 15); ``0`` disables the scheduler.

The API has no authentication and is meant for ``127.0.0.1`` only (D9).
Requests for any other ``Host`` are rejected, so a website using DNS rebinding
cannot reach the API through the user's browser.
"""

import asyncio
import contextlib
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from ai_radar.db import open_database
from ai_radar.feeds.api import router as feeds_router
from ai_radar.ingest.api import router as refresh_router
from ai_radar.ingest.scheduler import (
    IngestionRunner,
    fetch_interval_seconds,
    ingest_stored_feeds_once,
    run_periodically,
)
from ai_radar.security import LOCAL_HOSTS

DB_PATH_ENV = "AI_RADAR_DB"
FETCH_INTERVAL_ENV = "AI_RADAR_FETCH_INTERVAL_MINUTES"
DEFAULT_DB_PATH = "ai-radar.db"
ALLOWED_HOSTS = list(LOCAL_HOSTS)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Prepare the database, then run the feed scheduler until shutdown."""
    interval = fetch_interval_seconds(os.environ.get(FETCH_INTERVAL_ENV))
    db_path = Path(os.environ.get(DB_PATH_ENV, DEFAULT_DB_PATH))
    with open_database(db_path):  # create or migrate the schema once
        pass
    app.state.db_path = db_path
    app.state.ingestion = IngestionRunner(partial(ingest_stored_feeds_once, db_path))

    scheduler = None
    if interval is not None:
        scheduler = asyncio.create_task(
            run_periodically(app.state.ingestion, interval), name="feed-scheduler"
        )
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await scheduler


app = FastAPI(title="AI Radar", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
app.include_router(feeds_router)
app.include_router(refresh_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check: confirms the API process is running."""
    return {"status": "ok"}

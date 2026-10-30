"""HTTP API for starting a feed refresh manually: ``/api/refresh``.

A refresh shares the runner with the scheduler, so at most one pass runs at a
time, however it was started.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from ai_radar.ingest.scheduler import IngestionRunner
from ai_radar.security import require_local_origin

router = APIRouter(prefix="/api/refresh", tags=["refresh"])


class RefreshStatus(BaseModel):
    running: bool
    last_started_at: datetime | None
    last_finished_at: datetime | None


class RefreshStarted(BaseModel):
    status: str = "started"


def _runner(request: Request) -> IngestionRunner:
    return request.app.state.ingestion


# A POST without a body is a "simple" cross-site request, so it needs the
# origin check (the JSON endpoints are covered by the CORS preflight).
@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_local_origin)],
)
def start_refresh(request: Request) -> RefreshStarted:
    if not _runner(request).try_start():
        raise HTTPException(status.HTTP_409_CONFLICT, "A refresh is already running")
    return RefreshStarted()


@router.get("")
def refresh_status(request: Request) -> RefreshStatus:
    current = _runner(request).status()
    return RefreshStatus(
        running=current.running,
        last_started_at=current.last_started_at,
        last_finished_at=current.last_finished_at,
    )

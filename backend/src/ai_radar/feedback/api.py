"""HTTP API for article feedback: ``/api/articles/{id}/feedback``.

Like the other APIs, every request opens its own SQLite connection inside the
handler (``sqlite3`` connections must not cross threads).
"""

from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi import Path as PathParam
from pydantic import BaseModel, ConfigDict

from ai_radar.db import connect
from ai_radar.feedback.repository import FeedbackRepository, Rating

_NOT_FOUND = "Article not found"

ArticleId = Annotated[int, PathParam(ge=1, le=2**63 - 1)]  # SQLite INTEGER range

router = APIRouter(prefix="/api/articles", tags=["feedback"])


class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: Rating


class FeedbackOut(BaseModel):
    article_id: int
    rating: Rating
    created_at: datetime
    updated_at: datetime


@contextmanager
def _repository(request: Request) -> Iterator[FeedbackRepository]:
    db_path: Path = request.app.state.db_path
    with closing(connect(db_path)) as conn:
        yield FeedbackRepository(conn)


@router.put("/{article_id}/feedback")
def set_feedback(
    request: Request, article_id: ArticleId, body: FeedbackIn
) -> FeedbackOut:
    with _repository(request) as feedback:
        stored = feedback.set(article_id, body.rating)
    if stored is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)
    return FeedbackOut(
        article_id=stored.article_id,
        rating=stored.rating,
        created_at=stored.created_at,
        updated_at=stored.updated_at,
    )


@router.delete("/{article_id}/feedback", status_code=status.HTTP_204_NO_CONTENT)
def delete_feedback(request: Request, article_id: ArticleId) -> Response:
    with _repository(request) as feedback:
        found = feedback.remove(article_id)
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

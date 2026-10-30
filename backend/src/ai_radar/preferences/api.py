"""HTTP API for learned preferences: ``/api/preferences``.

Manual interests are served separately by ``/api/interests``.
"""

from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel

from ai_radar.db import connect
from ai_radar.preferences.repository import LearnedTopic, PreferenceRepository

router = APIRouter(prefix="/api/preferences", tags=["preferences"])


class LearnedPreferenceOut(BaseModel):
    topic: str
    score: int
    relevant: int  # the counts explain the score
    irrelevant: int
    ratings: int

    @classmethod
    def from_topic(cls, topic: LearnedTopic) -> "LearnedPreferenceOut":
        return cls(
            topic=topic.topic,
            score=topic.score,
            relevant=topic.relevant,
            irrelevant=topic.irrelevant,
            ratings=topic.ratings,
        )


class PreferencesOut(BaseModel):
    learned: list[LearnedPreferenceOut]
    last_reset_at: datetime | None


@contextmanager
def _repository(request: Request) -> Iterator[PreferenceRepository]:
    db_path: Path = request.app.state.db_path
    with closing(connect(db_path)) as conn:
        yield PreferenceRepository(conn)


@router.get("")
def get_preferences(request: Request) -> PreferencesOut:
    with _repository(request) as preferences:
        return PreferencesOut(
            learned=[LearnedPreferenceOut.from_topic(t) for t in preferences.learned()],
            last_reset_at=preferences.last_reset_at(),
        )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def reset_preferences(request: Request) -> Response:
    with _repository(request) as preferences:
        preferences.reset()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

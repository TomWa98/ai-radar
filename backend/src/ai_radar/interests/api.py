"""HTTP API for manual interests: ``/api/interests``.

Like the feed API, every request opens its own SQLite connection inside the
handler (``sqlite3`` connections must not cross threads).
"""

from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Self

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi import Path as PathParam
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_radar.analysis.models import InterestWeight
from ai_radar.db import connect
from ai_radar.interests.repository import (
    DuplicateInterestError,
    InterestRepository,
    StoredInterest,
    TooManyInterestsError,
    normalize_topic,
)

_DUPLICATE = "An interest with this topic already exists"
_NOT_FOUND = "Interest not found"

InterestId = Annotated[int, PathParam(ge=1, le=2**63 - 1)]  # SQLite INTEGER range
# Raw input limit; the normalized topic is checked by normalize_topic.
RawTopic = Annotated[str, Field(max_length=1000)]

router = APIRouter(prefix="/api/interests", tags=["interests"])


class InterestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: RawTopic
    weight: InterestWeight = InterestWeight.MEDIUM

    _topic = field_validator("topic")(normalize_topic)


class InterestUpdate(BaseModel):
    """Partial update: omitted fields stay unchanged."""

    model_config = ConfigDict(extra="forbid")

    topic: RawTopic | None = None
    weight: InterestWeight | None = None

    @field_validator("topic")
    @classmethod
    def _topic(cls, value: str | None) -> str | None:
        return None if value is None else normalize_topic(value)

    @model_validator(mode="after")
    def _no_null(self) -> Self:
        for field in ("topic", "weight"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} must not be null")
        return self


class InterestOut(BaseModel):
    id: int
    topic: str
    weight: InterestWeight
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_interest(cls, interest: StoredInterest) -> Self:
        return cls(
            id=interest.id,
            topic=interest.topic,
            weight=interest.weight,
            created_at=interest.created_at,
            updated_at=interest.updated_at,
        )


@contextmanager
def _repository(request: Request) -> Iterator[InterestRepository]:
    db_path: Path = request.app.state.db_path
    with closing(connect(db_path)) as conn:
        yield InterestRepository(conn)


@router.get("")
def list_interests(request: Request) -> list[InterestOut]:
    with _repository(request) as interests:
        return [InterestOut.from_interest(i) for i in interests.list_all()]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_interest(request: Request, body: InterestCreate) -> InterestOut:
    with _repository(request) as interests:
        try:
            interest = interests.add(body.topic, body.weight)
        except DuplicateInterestError:
            raise HTTPException(status.HTTP_409_CONFLICT, _DUPLICATE) from None
        except TooManyInterestsError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)
            ) from None
    return InterestOut.from_interest(interest)


@router.patch("/{interest_id}")
def update_interest(
    request: Request, interest_id: InterestId, body: InterestUpdate
) -> InterestOut:
    with _repository(request) as interests:
        try:
            interest = interests.update(
                interest_id, topic=body.topic, weight=body.weight
            )
        except DuplicateInterestError:
            raise HTTPException(status.HTTP_409_CONFLICT, _DUPLICATE) from None
    if interest is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)
    return InterestOut.from_interest(interest)


@router.delete("/{interest_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_interest(request: Request, interest_id: InterestId) -> Response:
    with _repository(request) as interests:
        removed = interests.remove(interest_id)
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

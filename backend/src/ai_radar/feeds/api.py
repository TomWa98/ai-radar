"""HTTP API for managing feeds: ``/api/feeds``.

Every request opens its own SQLite connection inside the handler. A
connection from a FastAPI dependency could be used from another worker
thread, which ``sqlite3`` does not allow.
"""

from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Self

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi import Path as PathParam
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_radar.articles.url import normalize_url
from ai_radar.db import connect
from ai_radar.feeds.models import Feed, NewFeed
from ai_radar.feeds.repository import DuplicateFeedError, FeedRepository

MAX_URL_LENGTH = 2048
MAX_NAME_LENGTH = 200

_DUPLICATE = "A feed with this URL already exists"
_NOT_FOUND = "Feed not found"

FeedId = Annotated[int, PathParam(ge=1, le=2**63 - 1)]  # SQLite INTEGER range

router = APIRouter(prefix="/api/feeds", tags=["feeds"])


def _check_url(value: str) -> str:
    value = value.strip()
    normalize_url(value)  # raises ValueError with a readable reason
    return value


def _clean_name(value: str | None) -> str | None:
    return (value.strip() or None) if value is not None else None


class FeedCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(max_length=MAX_URL_LENGTH)
    name: str | None = Field(default=None, max_length=MAX_NAME_LENGTH)
    enabled: bool = True
    fetch_full_text: bool = False

    _url = field_validator("url")(_check_url)
    _name = field_validator("name")(_clean_name)


class FeedUpdate(BaseModel):
    """Partial update: omitted fields stay unchanged; ``name: null`` clears it."""

    model_config = ConfigDict(extra="forbid")

    url: str | None = Field(default=None, max_length=MAX_URL_LENGTH)
    name: str | None = Field(default=None, max_length=MAX_NAME_LENGTH)
    enabled: bool | None = None
    fetch_full_text: bool | None = None

    @field_validator("url")
    @classmethod
    def _url(cls, value: str | None) -> str | None:
        return None if value is None else _check_url(value)

    _name = field_validator("name")(_clean_name)

    @model_validator(mode="after")
    def _no_null_for_required_fields(self) -> Self:
        for field in ("url", "enabled", "fetch_full_text"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} must not be null")
        return self


class FeedOut(BaseModel):
    id: int
    url: str
    name: str | None
    enabled: bool
    fetch_full_text: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_feed(cls, feed: Feed) -> Self:
        return cls(
            id=feed.id,
            url=feed.url,
            name=feed.name,
            enabled=feed.enabled,
            fetch_full_text=feed.fetch_full_text,
            created_at=feed.created_at,
            updated_at=feed.updated_at,
        )


@contextmanager
def _repository(request: Request) -> Iterator[FeedRepository]:
    db_path: Path = request.app.state.db_path
    with closing(connect(db_path)) as conn:
        yield FeedRepository(conn)


def _duplicate() -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, _DUPLICATE)


@router.get("")
def list_feeds(request: Request) -> list[FeedOut]:
    with _repository(request) as feeds:
        return [FeedOut.from_feed(feed) for feed in feeds.list_all()]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_feed(request: Request, body: FeedCreate) -> FeedOut:
    new = NewFeed(
        url=body.url,
        name=body.name,
        enabled=body.enabled,
        fetch_full_text=body.fetch_full_text,
    )
    with _repository(request) as feeds:
        try:
            feed = feeds.add(new)
        except DuplicateFeedError:
            raise _duplicate() from None
    return FeedOut.from_feed(feed)


@router.patch("/{feed_id}")
def update_feed(request: Request, feed_id: FeedId, body: FeedUpdate) -> FeedOut:
    with _repository(request) as feeds:
        current = feeds.get_by_id(feed_id)
        if current is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)
        changes = body.model_dump(exclude_unset=True)
        new = NewFeed(
            url=changes.get("url", current.url),
            name=changes.get("name", current.name),
            enabled=changes.get("enabled", current.enabled),
            fetch_full_text=changes.get("fetch_full_text", current.fetch_full_text),
        )
        try:
            feed = feeds.update(feed_id, new)
        except DuplicateFeedError:
            raise _duplicate() from None
    if feed is None:  # removed concurrently
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)
    return FeedOut.from_feed(feed)


@router.delete("/{feed_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_feed(request: Request, feed_id: FeedId) -> Response:
    with _repository(request) as feeds:
        removed = feeds.remove(feed_id)
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

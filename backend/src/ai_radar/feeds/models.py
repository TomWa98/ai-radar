"""Feed data model, independent of storage and API."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class NewFeed:
    """The user-editable fields of a feed."""

    url: str
    name: str | None = None
    enabled: bool = True
    fetch_full_text: bool = False  # opt-in per feed (D3)


@dataclass(frozen=True, slots=True)
class Feed:
    """A stored feed."""

    id: int
    url: str
    normalized_url: str
    name: str | None
    enabled: bool
    fetch_full_text: bool
    created_at: datetime
    updated_at: datetime

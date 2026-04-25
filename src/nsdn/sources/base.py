"""EntrySource ABC and FeedEntry model."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class FeedEntry(BaseModel):
    source_type: str
    source_name: str
    guid: str
    title: str
    summary: str | None = None
    content: str | None = None
    link: str | None = None
    published_at: datetime | None = None
    author: str | None = None
    tags: list[str] = []
    images: list[str] = []


class EntrySource(ABC):
    source_type: str

    def __init__(self, name: str, config: dict[str, Any]):
        self.name = name
        self.config = config

    @abstractmethod
    def fetch(self) -> list[FeedEntry]:
        """Fetch entries and return standardized FeedEntry objects."""
        ...

    def validate(self) -> bool:
        """Optional pre-flight check (e.g., connectivity, auth)."""
        return True

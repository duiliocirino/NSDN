"""HighlightSelector ABC and implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from nsdn.sources.base import FeedEntry

if TYPE_CHECKING:
    pass

SELECTOR_REGISTRY: dict[str, type] = {}


def register_selector(name: str, cls: type) -> None:
    SELECTOR_REGISTRY[name] = cls


def get_selector(name: str) -> type:
    if name not in SELECTOR_REGISTRY:
        raise ValueError(f"Unknown highlight selector: {name}. Available: {list(SELECTOR_REGISTRY.keys())}")
    return SELECTOR_REGISTRY[name]


class HighlightSelector(ABC):
    """Abstract base for selecting highlight entries from clustered topics."""

    @abstractmethod
    def select(self, entries_by_topic: dict[str, list[FeedEntry]]) -> list[FeedEntry]:
        """Select highlight entries for the cover page."""
        ...


class TopScorePerTopic(HighlightSelector):
    """Select the highest-scored entry from each topic."""

    def select(self, entries_by_topic: dict[str, list[FeedEntry]]) -> list[FeedEntry]:
        highlights: list[FeedEntry] = []
        for entries in entries_by_topic.values():
            if entries:
                best = max(entries, key=lambda e: e.score)
                highlights.append(best)
        return highlights


# Auto-register default selector
register_selector("top_score", TopScorePerTopic)

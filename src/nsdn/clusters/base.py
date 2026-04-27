"""Base clustering strategy."""

from __future__ import annotations

from abc import ABC, abstractmethod

from nsdn.config import AppConfig
from nsdn.sources.base import FeedEntry


class ClusterStrategy(ABC):
    """Abstract base for clustering strategies."""

    def __init__(self, config: AppConfig):
        self.config = config

    @abstractmethod
    def cluster(self, entries: list[FeedEntry]) -> dict[str, list[FeedEntry]]:
        """Cluster entries and return dict mapping topic → entries."""
        ...

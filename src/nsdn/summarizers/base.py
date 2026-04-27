"""Base summarization strategy."""

from __future__ import annotations

from abc import ABC, abstractmethod

from nsdn.db import Database
from nsdn.llm import LLMProvider


class SummarizerStrategy(ABC):
    """Abstract base for summarization strategies."""

    def __init__(self, config):
        self.config = config

    @abstractmethod
    def summarize(self, db: Database, llm: LLMProvider | None = None) -> dict[str, int]:
        """Summarize entries and return stats."""
        ...

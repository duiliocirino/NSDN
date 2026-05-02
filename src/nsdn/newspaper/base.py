"""NewspaperStrategy ABC."""

from __future__ import annotations

from abc import ABC, abstractmethod

from nsdn.config import AppConfig
from nsdn.db import Database
from nsdn.llm import LLMProvider
from nsdn.sources.base import FeedEntry


class NewspaperStrategy(ABC):
    """Abstract base for newspaper design strategies."""

    def __init__(self, config: AppConfig, design_llm: LLMProvider, evaluate_llm: LLMProvider | None = None):
        self.config = config
        self.design_llm = design_llm
        self.evaluate_llm = evaluate_llm

    @abstractmethod
    def run_design(self, db: Database) -> dict:
        """Run the full design pipeline: cluster → topic pages → cover → assemble."""
        ...

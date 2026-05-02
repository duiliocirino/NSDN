"""CoverDesigner — front page from cluster highlights."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from nsdn.config import AppConfig
from nsdn.llm import LLMProvider
from nsdn.newspaper.generator import LayoutGenerator
from nsdn.newspaper.selectors import get_selector, TopScorePerTopic
from nsdn.sources.base import FeedEntry


class CoverDesigner:
    """Designs the edition cover page from clustered entries."""

    def __init__(self, config: AppConfig, generator: LayoutGenerator):
        self.config = config
        self.generator = generator

    def design(self, entries_by_topic: dict[str, list[FeedEntry]]) -> tuple[str, str]:
        """Design cover page.

        Returns:
            (html, css)
        """
        selector = self._get_selector()
        highlights = selector.select(entries_by_topic)
        date_str = date.today().isoformat()
        slot = self._get_slot()
        return self.generator.generate_cover(highlights, entries_by_topic, date_str, slot)

    def _get_selector(self) -> TopScorePerTopic:
        """Get the highlight selector instance."""
        # For now, always use TopScorePerTopic
        # Future: configurable via config.newspaper.cover.selector
        selector_cls = get_selector("top_score")
        return selector_cls()

    @staticmethod
    def _get_slot() -> str:
        """Get time slot from current hour."""
        hour = datetime.now().hour
        if hour < 12:
            return "morning"
        elif hour < 17:
            return "afternoon"
        else:
            return "evening"

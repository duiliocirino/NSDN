"""PageDesigner ABC."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from nsdn.sources.base import FeedEntry


class PageDesigner(ABC):
    designer_type: str

    def __init__(self, config: dict[str, Any]):
        self.config = config

    @abstractmethod
    def get_template_path(self) -> str:
        """Return path to the Jinja2 template file."""
        ...

    @abstractmethod
    def get_css(self) -> str:
        """Return CSS string (for inline) or empty string (for linked)."""
        ...

    def get_css_url(self) -> str:
        """Return external CSS URL. Override if using linked CSS."""
        return ""

    def render_entry(self, entry: FeedEntry) -> str:
        """Render a single entry to Markdown. Override for custom formatting."""
        lines = [f"### {entry.title}"]
        if entry.images:
            lines.append(f"![{entry.title}]({entry.images[0]})")
        if entry.summary:
            lines.append(f"> {entry.summary}")
        if entry.link:
            lines.append(f"— [{entry.source_name} ↗]({entry.link})")
        return "\n".join(lines)

    def render_edition(self, entries_by_topic: dict[str, list[FeedEntry]], edition_date: str, slot: str) -> str:
        """Assemble full Markdown content from grouped entries."""
        sections: list[str] = []
        for topic, entries in entries_by_topic.items():
            sections.append(f"## {topic}")
            for entry in entries:
                sections.append(self.render_entry(entry))
        return "\n\n".join(sections)

    def get_context(self, content: str, edition_date: str, slot: str) -> dict[str, Any]:
        """Build Jinja2 template context."""
        return {
            "title": f"NSDN — {edition_date} ({slot})",
            "date": edition_date,
            "slot": slot,
            "content": content,
            "css": self.get_css(),
            "css_url": self.get_css_url(),
            "inline_css": bool(self.get_css()),
        }

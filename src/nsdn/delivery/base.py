"""DeliveryTarget ABC and ContentInfo model."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from nsdn.config import DeliveryResult


class ContentInfo(BaseModel):
    """Assembled content ready for delivery."""

    date: str
    slot: str
    topics: list[str]
    entry_count: int
    pdf_path: Path | None = None
    mobile_pdf_path: Path | None = None
    caption: str = ""


class DeliveryTarget(ABC):
    """Base class for all delivery targets.

    Matches EntrySource instantiation pattern: label + config dict.
    Subclasses set `target_type` as a class attribute and implement `deliver()`.
    """

    target_type: str

    def __init__(self, label: str, config: dict[str, Any]):
        self.label = label
        self.config = config

    @abstractmethod
    def deliver(self, content_info: ContentInfo) -> DeliveryResult:
        """Send content_info to the target and return a result."""
        ...

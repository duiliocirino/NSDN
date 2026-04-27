"""Summarization strategy registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nsdn.sources.base import FeedEntry

if TYPE_CHECKING:
    from nsdn.config import AppConfig

SUMMARIZER_REGISTRY: dict[str, type] = {}


def register_summarizer(strategy_type: str, strategy_class: type) -> None:
    SUMMARIZER_REGISTRY[strategy_type] = strategy_class


def get_summarizer(strategy_type: str):
    if strategy_type not in SUMMARIZER_REGISTRY:
        raise ValueError(f"Unknown summarizer strategy: {strategy_type}. Available: {list(SUMMARIZER_REGISTRY.keys())}")
    return SUMMARIZER_REGISTRY[strategy_type]


def run_summarize(config: AppConfig, db, llm=None) -> dict[str, int]:
    """Dispatch to the configured summarization strategy."""
    strategy_type = config.summarize.strategy
    strategy_cls = get_summarizer(strategy_type)
    return strategy_cls(config).summarize(db, llm=llm)


# Import implementations to register them
import nsdn.summarizers.llm_summarizer  # noqa: F401

"""Summarization strategy registry."""

from __future__ import annotations

from nsdn.summarizers.base import SummarizerStrategy

SUMMARIZER_REGISTRY: dict[str, type[SummarizerStrategy]] = {}


def register_summarizer(strategy_type: str, strategy_class: type[SummarizerStrategy]) -> None:
    SUMMARIZER_REGISTRY[strategy_type] = strategy_class


def get_summarizer(strategy_type: str) -> type[SummarizerStrategy]:
    if strategy_type not in SUMMARIZER_REGISTRY:
        available = ", ".join(SUMMARIZER_REGISTRY.keys()) or "(none)"
        raise ValueError(f"Unknown summarizer strategy: {strategy_type}. Available: {available}")
    return SUMMARIZER_REGISTRY[strategy_type]


def run_summarize(config: AppConfig, db, llm=None) -> dict[str, int]:
    """Dispatch to the configured summarization strategy."""
    strategy_type = config.summarize.strategy
    strategy_cls = get_summarizer(strategy_type)
    return strategy_cls(config).summarize(db, llm=llm)


# Import implementations to register them
import nsdn.summarizers.llm_summarizer  # noqa: F401

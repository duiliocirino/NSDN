"""Clustering strategy registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nsdn.llm import LLMProvider
from nsdn.sources.base import FeedEntry

if TYPE_CHECKING:
    from nsdn.config import AppConfig

CLUSTER_REGISTRY: dict[str, type] = {}


def register_cluster(strategy_type: str, strategy_class: type) -> None:
    CLUSTER_REGISTRY[strategy_type] = strategy_class


def get_cluster(strategy_type: str):
    if strategy_type not in CLUSTER_REGISTRY:
        raise ValueError(f"Unknown cluster strategy: {strategy_type}. Available: {list(CLUSTER_REGISTRY.keys())}")
    return CLUSTER_REGISTRY[strategy_type]


def run_cluster(config: AppConfig, entries: list[FeedEntry], llm: LLMProvider | None = None) -> dict[str, list[FeedEntry]]:
    """Dispatch to the configured clustering strategy."""
    strategy_type = config.synthesize.cluster_strategy
    strategy_cls = get_cluster(strategy_type)
    return strategy_cls(config).cluster(entries, llm=llm)


# Import implementations to register them
import nsdn.clusters.llm_cluster  # noqa: F401

"""Clustering strategy registry."""

from __future__ import annotations

from nsdn.clusters.base import ClusterStrategy
from nsdn.llm import LLMProvider
from nsdn.sources.base import FeedEntry

CLUSTER_REGISTRY: dict[str, type[ClusterStrategy]] = {}


def register_cluster(strategy_type: str, strategy_class: type[ClusterStrategy]) -> None:
    CLUSTER_REGISTRY[strategy_type] = strategy_class


def get_cluster(strategy_type: str) -> type[ClusterStrategy]:
    if strategy_type not in CLUSTER_REGISTRY:
        available = ", ".join(CLUSTER_REGISTRY.keys()) or "(none)"
        raise ValueError(f"Unknown cluster strategy: {strategy_type}. Available: {available}")
    return CLUSTER_REGISTRY[strategy_type]


def run_cluster(config: AppConfig, entries: list[FeedEntry], llm: LLMProvider | None = None) -> dict[str, list[FeedEntry]]:
    """Dispatch to the configured clustering strategy."""
    strategy_type = config.synthesize.cluster_strategy
    strategy_cls = get_cluster(strategy_type)
    return strategy_cls(config).cluster(entries, llm=llm)


# Import implementations to register them
import nsdn.clusters.llm_cluster  # noqa: F401

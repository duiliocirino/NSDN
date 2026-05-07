"""LLM-based clustering strategy."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from nsdn.clusters.base import ClusterStrategy
from nsdn.clusters import register_cluster
from nsdn.config import AppConfig
from nsdn.prompts import CLUSTER_SYSTEM_PROMPT, build_cluster_prompt
from nsdn.sources.base import FeedEntry

logger = logging.getLogger(__name__)


class ClusterResult(BaseModel):
    topics: dict[str, list[str]]  # topic_name → [guids]
    limits: dict[str, int]  # topic_name → how many to feature


class LLMClusterStrategy(ClusterStrategy):
    """Cluster entries using LLM topic assignment."""

    def cluster(self, entries: list[FeedEntry], llm: Any = None) -> dict[str, list[FeedEntry]]:
        if not entries:
            return {}

        if llm is None:
            return {"General": entries}

        entry_dicts = [
            {"guid": e.guid, "title": e.title, "summary": e.summary or ""}
            for e in entries
        ]
        prompt = build_cluster_prompt(entry_dicts)

        try:
            result = llm.invoke_structured(
                prompt, ClusterResult, system_message=CLUSTER_SYSTEM_PROMPT, temperature=self.config.llm.get("cluster").temperature
            )
        except Exception as exc:
            logger.error("Clustering failed: %s", exc)
            return {"General": entries}

        entry_map = {e.guid: e for e in entries}
        groups: dict[str, list[FeedEntry]] = {}

        for topic, guids in result.topics.items():
            groups[topic] = [entry_map[g] for g in guids if g in entry_map]

        # Apply per-topic limits
        limits = result.limits
        for topic in groups:
            if topic in limits:
                groups[topic] = groups[topic][: limits[topic]]

        # Remove empty topics (LLM can return topics with invalid/empty guids)
        groups = {topic: entries for topic, entries in groups.items() if entries}

        # Soft cap: if too many topics, drop smallest
        max_sections = self.config.synthesize.max_sections
        if len(groups) > max_sections:
            sorted_topics = sorted(groups.items(), key=lambda x: len(x[1]), reverse=True)
            groups = dict(sorted_topics[:max_sections])

        # If all topics were empty, fall back to single "General" topic
        if not groups:
            logger.warning("Clustering produced no valid topics — falling back to General")
            return {"General": entries}

        return groups


register_cluster("llm", LLMClusterStrategy)

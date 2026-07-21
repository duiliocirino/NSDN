"""Weaviate semantic engine."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import weaviate

from nsdn.sources.base import FeedEntry

logger = logging.getLogger(__name__)


class VectorStore:
    """Weaviate client wrapper for semantic operations."""

    def __init__(self, config: Any):
        self.config = config
        self.client = None
        self.collection = None

        if not config.enabled:
            logger.info("Weaviate disabled in config")
            return

        try:
            parsed = urlparse(config.url)
            host = parsed.hostname or "localhost"
            port = parsed.port or 8050
            self.client = weaviate.connect_to_local(
                host=host,
                port=port,
            )
            self._ensure_collection()
        except Exception as exc:
            logger.warning("Weaviate unavailable: %s — semantic features disabled", exc)
            self.client = None

    def _ensure_collection(self) -> None:
        """Create or get the NSDNEntries collection."""
        from weaviate.classes.config import Configure, DataType, Property

        assert self.client is not None

        name = self.config.collection_name
        if name not in self.client.collections:
            self.collection = self.client.collections.create(
                name=name,
                vector_config=Configure.Vectors.text2vec_ollama(
                    model=self.config.embedding_model,
                    api_endpoint=self.config.embedding_endpoint,
                ),
                properties=[
                    Property(name="guid", data_type=DataType.TEXT, skip_vectorization=True),
                    Property(name="title", data_type=DataType.TEXT, skip_vectorization=True),
                    Property(name="summary", data_type=DataType.TEXT, skip_vectorization=True),
                    Property(name="source_name", data_type=DataType.TEXT, skip_vectorization=True),
                    Property(name="published_at", data_type=DataType.TEXT, skip_vectorization=True),
                    Property(name="semantic_text", data_type=DataType.TEXT),
                ],
            )
        else:
            self.collection = self.client.collections.get(name)

    def add_entry(self, entry: FeedEntry) -> None:
        """Add an entry to Weaviate for semantic operations."""
        if self.collection is None:
            return
        semantic_text = f"{entry.title} {entry.summary or ''}".strip()
        self.collection.data.insert(
            properties={
                "guid": entry.guid,
                "title": entry.title,
                "summary": entry.summary or "",
                "source_name": entry.source_name,
                "published_at": entry.published_at.isoformat() if entry.published_at else "",
                "semantic_text": semantic_text,
            },
        )

    def is_duplicate(self, entry: FeedEntry, threshold: float | None = None) -> bool:
        """Check if an entry is semantically similar to existing entries."""
        if self.collection is None:
            return False
        threshold = threshold or self.config.dedup_threshold
        semantic_text = f"{entry.title} {entry.summary or ''}".strip()
        results = self.collection.query.near_text(
            query=semantic_text,
            limit=1
        )
        for obj in results.objects:
            dist = obj.metadata.distance
            if dist is not None and threshold and dist < (1 - threshold):
                if obj.properties.get("guid") != entry.guid:
                    return True
        return False

    def search_by_interest(self, interest: str, limit: int = 50) -> list[Any]:
        """Search entries by interest text."""
        if self.collection is None:
            return []
        results = self.collection.query.near_text(
            query=interest,
            limit=limit,
        )
        return list(results.objects)

    def close(self) -> None:
        if self.client:
            self.client.close()

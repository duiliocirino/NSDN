"""Extract pipeline — orchestrates all sources → SQLite + Weaviate."""

from __future__ import annotations

import logging
import time

from nsdn.config import AppConfig, SourceConfig
from nsdn.db import Database
from nsdn.sources import get_source
from nsdn.sources.base import FeedEntry
from nsdn.vector import VectorStore

logger = logging.getLogger(__name__)

# Small delay between sources to avoid hammering feed providers
INTER_SOURCE_DELAY = 1.0


def run_extract(config: AppConfig, db: Database, vector: VectorStore | None = None) -> dict[str, int]:
    """Run extract for all configured sources.

    Returns dict mapping source name to number of new entries inserted.
    """
    stats: dict[str, int] = {}

    for src_cfg in config.sources:
        source_class = get_source(src_cfg.type)
        source = source_class(src_cfg.name, src_cfg.config)

        logger.info("Processing source: %s (type=%s)", src_cfg.name, src_cfg.type)

        # Validate source
        if not source.validate():
            logger.warning("Source %s failed validation, skipping", src_cfg.name)
            stats[src_cfg.name] = 0
            continue

        # Fetch entries
        entries = source.fetch()
        logger.info("Source %s returned %d entries", src_cfg.name, len(entries))

        # Upsert source in DB
        source_id = db.upsert_source(src_cfg.type, src_cfg.name, src_cfg.config)

        # Filter by max_items_per_feed
        max_items = config.filter_.max_items_per_feed
        if len(entries) > max_items:
            logger.info("Truncating %s from %d to %d items", src_cfg.name, len(entries), max_items)
            entries = entries[:max_items]

        # Semantic deduplication via Weaviate
        if vector:
            entries = _semantic_dedup(entries, vector)

        # Insert into SQLite
        inserted = db.insert_entries(entries, source_id)
        stats[src_cfg.name] = inserted
        logger.info("Inserted %d new entries from %s (skipped %d duplicates)", inserted, src_cfg.name, len(entries) - inserted)

        # Index in Weaviate
        if vector:
            for entry in entries:
                vector.add_entry(entry)

        # Small delay between sources to avoid hammering providers
        time.sleep(INTER_SOURCE_DELAY)

    return stats


def _semantic_dedup(entries: list[FeedEntry], vector: VectorStore) -> list[FeedEntry]:
    """Remove entries that are semantically duplicates of existing entries."""
    deduped: list[FeedEntry] = []
    skipped = 0
    for entry in entries:
        if not vector.is_duplicate(entry):
            deduped.append(entry)
        else:
            skipped += 1
    if skipped:
        logger.info("Semantic dedup: skipped %d entries", skipped)
    return deduped

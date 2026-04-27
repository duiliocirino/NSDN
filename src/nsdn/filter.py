"""LLM scoring — filter entries by relevance."""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel

from nsdn.config import AppConfig
from nsdn.db import Database
from nsdn.llm import LLMProvider
from nsdn.prompts import (
    FILTER_SEQUENTIAL_SYSTEM_PROMPT,
    FILTER_SYSTEM_PROMPT,
    build_filter_prompt,
)
from nsdn.sources.base import FeedEntry

logger = logging.getLogger(__name__)


class ScoreResult(BaseModel):
    scores: dict[str, int]  # guid → score


def run_filter(config: AppConfig, db: Database, llm: LLMProvider) -> dict[str, Any]:
    """Score all unscored entries and mark kept/discarded."""
    entries = db.get_new_entries()
    if not entries:
        logger.info("No unscored entries")
        return {"scored": 0, "kept": 0}

    logger.info("Scoring %d entries (mode=%s)", len(entries), config.filter_.mode)

    if config.filter_.mode == "batch":
        return _filter_batch(config, db, llm, entries)
    else:
        return _filter_sequential(config, db, llm, entries)


def _filter_sequential(
    config: AppConfig, db: Database, llm: LLMProvider, entries: list[FeedEntry]
) -> dict[str, Any]:
    """Score entries one at a time."""
    system = FILTER_SEQUENTIAL_SYSTEM_PROMPT.format(
        interests="\n".join(f"- {i}" for i in config.interests)
    )
    scored: dict[str, int] = {}
    threshold = config.filter_.score_threshold

    for entry in entries:
        tags = ", ".join(entry.tags) if entry.tags else "(none)"
        prompt = f"Title: {entry.title}\nSummary: {entry.summary or '(none)'}\nSource: {entry.source_name}\nTags: {tags}"
        try:
            resp = llm.invoke(prompt, system_message=system, temperature=config.llm.get("filter").temperature)
            # Extract integer from response
            score = _parse_score(resp)
        except Exception as exc:
            logger.warning("Score failed for %s: %s", entry.guid, exc)
            score = 0  # Fail conservative
        scored[entry.guid] = score

    _persist_scores(db, scored, threshold)
    kept = sum(1 for s in scored.values() if s >= threshold)
    logger.info("Scored %d entries, kept %d (threshold=%d)", len(scored), kept, threshold)
    return {"scored": len(scored), "kept": kept}


def _filter_batch(
    config: AppConfig, db: Database, llm: LLMProvider, entries: list[FeedEntry]
) -> dict[str, Any]:
    """Score entries in batches using structured output."""
    threshold = config.filter_.score_threshold
    batch_size = config.filter_.batch_size
    system = FILTER_SYSTEM_PROMPT.format(
        interests="\n".join(f"- {i}" for i in config.interests)
    )
    all_scores: dict[str, int] = {}

    for i in range(0, len(entries), batch_size):
        batch = entries[i : i + batch_size]
        batch_dicts = [
            {
                "guid": e.guid,
                "title": e.title,
                "summary": e.summary,
                "source": e.source_name,
                "tags": e.tags,
            }
            for e in batch
        ]
        prompt = build_filter_prompt(batch_dicts)
        try:
            result = llm.invoke_structured(prompt, ScoreResult, system_message=system, temperature=config.llm.get("filter").temperature)
            all_scores.update(result.scores)
        except Exception as exc:
            logger.warning("Batch score failed at offset %d: %s", i, exc)
            # Fallback: score each entry in the batch individually
            for entry in batch:
                all_scores[entry.guid] = 0

    _persist_scores(db, all_scores, threshold)
    kept = sum(1 for s in all_scores.values() if s >= threshold)
    logger.info("Scored %d entries, kept %d (threshold=%d)", len(all_scores), kept, threshold)
    return {"scored": len(all_scores), "kept": kept}


def _persist_scores(db: Database, scores: dict[str, int], threshold: int) -> None:
    """Update scores in SQLite and mark kept entries."""
    for guid, score in scores.items():
        kept = 1 if score >= threshold else 0
        db.conn.execute(
            "UPDATE entries SET score = ?, kept = ? WHERE guid = ?",
            (score, kept, guid),
        )
    db.conn.commit()


def _parse_score(text: str) -> int:
    """Extract an integer score from LLM response."""
    text = text.strip()
    # Try direct int
    try:
        val = int(text)
        return max(0, min(10, val))
    except ValueError:
        pass
    # Try to find a number in the text
    for ch in text:
        if ch.isdigit():
            return int(ch)
    return 0

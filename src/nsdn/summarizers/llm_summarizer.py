"""LLM-based summarization strategy."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from nsdn.db import Database
from nsdn.llm import LLMProvider
from nsdn.prompts import SUMMARIZE_SYSTEM_PROMPT, build_summarize_prompt
from nsdn.summarizers.base import SummarizerStrategy
from nsdn.summarizers import register_summarizer

logger = logging.getLogger(__name__)


class SummaryResult(BaseModel):
    summaries: dict[str, str]  # guid → summary


class LLMSummarizerStrategy(SummarizerStrategy):
    """Summarize entries using LLM structured output."""

    def summarize(self, db: Database, llm: LLMProvider | None = None) -> dict[str, int]:
        if not self.config.summarize.enabled:
            return {"summarized": 0, "skipped": 0}

        entries = self._get_entries_needing_summary(db)
        if not entries:
            logger.info("No entries need summarization")
            return {"summarized": 0, "skipped": 0}

        if llm is None:
            logger.warning("No LLM provider available, skipping summarization")
            return {"summarized": 0, "skipped": len(entries)}

        batch_size = self.config.summarize.batch_size
        max_content = self.config.summarize.max_content_chars
        max_summary = self.config.summarize.max_summary_chars
        temperature = self.config.llm.get("summarize").temperature
        system = SUMMARIZE_SYSTEM_PROMPT.format(max_summary_chars=max_summary)

        logger.info("Summarizing %d entries (batch_size=%d, max_content=%d, max_summary=%d)",
                    len(entries), batch_size, max_content, max_summary)

        summarized = 0
        skipped = 0

        for i in range(0, len(entries), batch_size):
            batch = entries[i:i + batch_size]
            try:
                summaries = self._summarize_batch(llm, batch, max_content, max_summary, system, temperature)
                self._persist_summaries(db, summaries)
                summarized += len(summaries)
            except Exception as exc:
                logger.warning("Summarize batch failed at offset %d: %s", i, exc)
                skipped += len(batch)

        logger.info("Summarized %d entries, skipped %d", summarized, skipped)
        return {"summarized": summarized, "skipped": skipped}

    def _get_entries_needing_summary(self, db: Database) -> list[dict[str, Any]]:
        """Find unsummarized entries where content exceeds min_length."""
        min_length = self.config.summarize.min_length
        rows = db.conn.execute(
            "SELECT guid, content FROM entries WHERE content IS NOT NULL AND LENGTH(content) > ? AND summarized = 0",
            (min_length,),
        ).fetchall()
        return [{"guid": row[0], "content": row[1][:self.config.summarize.max_content_chars]} for row in rows]

    def _summarize_batch(
        self, llm: LLMProvider, batch: list[dict], max_content: int, max_summary: int, system: str, temperature: float
    ) -> dict[str, str]:
        """Summarize a batch of entries using structured LLM output."""
        prompt = build_summarize_prompt(batch, max_summary)
        result = llm.invoke_structured(prompt, SummaryResult, system_message=system, temperature=temperature)
        return result.summaries

    def _persist_summaries(self, db: Database, summaries: dict[str, str]) -> None:
        """Write summaries back to the database and mark as summarized."""
        for guid, summary in summaries.items():
            db.conn.execute("UPDATE entries SET summary = ?, summarized = 1 WHERE guid = ?", (summary, guid))
        db.conn.commit()


register_summarizer("llm", LLMSummarizerStrategy)

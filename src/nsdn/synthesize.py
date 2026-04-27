"""LLM synthesis — cluster entries and write journal."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

from nsdn.clusters import run_cluster
from nsdn.config import AppConfig
from nsdn.db import Database
from nsdn.designers import get_designer
from nsdn.llm import LLMProvider
from nsdn.prompts import EDITOR_SYSTEM_PROMPT, build_editor_prompt
from nsdn.sources.base import FeedEntry

logger = logging.getLogger(__name__)


def run_synthesize(config: AppConfig, db: Database, llm: LLMProvider) -> dict[str, Any]:
    """Cluster and write journal edition."""
    entries = db.get_kept_entries(processed=False)
    if not entries:
        logger.info("No kept entries to synthesize")
        return {"entries": 0, "sections": 0, "md_file": "", "html_file": ""}

    logger.info("Synthesizing %d kept entries (mode=%s)", len(entries), config.synthesize.mode)

    # Step 1: Cluster
    entries_by_topic = _cluster(config, llm, entries)
    if not entries_by_topic:
        logger.warning("Clustering produced no topics")
        return {"entries": len(entries), "sections": 0, "md_file": "", "html_file": ""}

    logger.info("Clustered into %d topics: %s", len(entries_by_topic), list(entries_by_topic.keys()))

    # Step 2: Write
    if config.synthesize.mode == "llm":
        return _write_llm(config, db, llm, entries, entries_by_topic)
    else:
        return _write_raw(config, db, entries, entries_by_topic)


def _cluster(config: AppConfig, llm: LLMProvider, entries: list[FeedEntry]) -> dict[str, list[FeedEntry]]:
    """Cluster entries by topic using configured strategy."""
    try:
        groups = run_cluster(config, entries, llm=llm)
        return groups
    except Exception as exc:
        logger.error("Clustering failed: %s", exc)
        return {"General": entries}


def _write_llm(
    config: AppConfig, db: Database, llm: LLMProvider, entries: list[FeedEntry], entries_by_topic: dict[str, list[FeedEntry]]
) -> dict[str, Any]:
    """Write journal using LLM synthesis."""
    sections: list[str] = []

    for topic, topic_entries in entries_by_topic.items():
        entry_dicts = [
            {
                "title": e.title,
                "summary": e.summary or "",
                "link": e.link or "",
                "source": e.source_name,
                "images": e.images,
            }
            for e in topic_entries
        ]
        system = EDITOR_SYSTEM_PROMPT.format(topic=topic)
        prompt = build_editor_prompt(topic, entry_dicts)
        try:
            content = llm.invoke(prompt, system_message=system, temperature=config.llm.get("synthesize").temperature)
            sections.append(f"## {topic}\n\n{content}")
        except Exception as exc:
            logger.warning("Editor failed for topic '%s': %s — using raw fallback", topic, exc)
            sections.append(f"## {topic}\n\n" + "\n\n".join(f"- {e.title}" for e in topic_entries))

    md_content = "\n\n".join(sections)
    edition_date = date.today().isoformat()
    slot = _get_slot()

    # Write Markdown
    output_dir = Path(config.output.directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    md_file = output_dir / f"{config.synthesize.mode}-{edition_date}-{slot}.md"
    md_file.write_text(md_content, encoding="utf-8")

    # Render HTML
    html_file = _render(config, md_content, edition_date, slot, output_dir)

    # Mark entries as processed
    guids = [e.guid for e in entries]
    db.mark_processed(guids, edition_date, slot)
    db.record_edition(edition_date, slot, str(md_file), str(html_file), len(entries))

    logger.info("Wrote edition: %s (%d entries, %d sections)", md_file, len(entries), len(sections))
    return {
        "entries": len(entries),
        "sections": len(sections),
        "md_file": str(md_file),
        "html_file": str(html_file),
    }


def _write_raw(
    config: AppConfig, db: Database, entries: list[FeedEntry], entries_by_topic: dict[str, list[FeedEntry]]
) -> dict[str, Any]:
    """Write journal using raw passthrough (no LLM)."""
    designer_class = get_designer(config.output.designer)
    designer = designer_class(config.output.model_dump() if hasattr(config.output, 'model_dump') else {})

    md_content = designer.render_edition(entries_by_topic, date.today().isoformat(), _get_slot())
    edition_date = date.today().isoformat()
    slot = _get_slot()

    output_dir = Path(config.output.directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    md_file = output_dir / f"{config.synthesize.mode}-{edition_date}-{slot}.md"
    md_file.write_text(md_content, encoding="utf-8")

    html_file = _render(config, md_content, edition_date, slot, output_dir)

    guids = [e.guid for e in entries]
    db.mark_processed(guids, edition_date, slot)
    db.record_edition(edition_date, slot, str(md_file), str(html_file), len(entries))

    logger.info("Wrote raw edition: %s (%d entries, %d topics)", md_file, len(entries), len(entries_by_topic))
    return {
        "entries": len(entries),
        "sections": len(entries_by_topic),
        "md_file": str(md_file),
        "html_file": str(html_file),
    }


def _render(
    config: AppConfig, md_content: str, edition_date: str, slot: str, output_dir: Path
) -> Path:
    """Render Markdown → HTML using designer."""
    import mistune
    from jinja2 import Environment, FileSystemLoader

    html_body = mistune.html(md_content)

    designer_class = get_designer(config.output.designer)
    designer_cfg = config.output.model_dump() if hasattr(config.output, "model_dump") else {}
    designer = designer_class(designer_cfg)
    ctx = designer.get_context(html_body, edition_date, slot)

    env = Environment(loader=FileSystemLoader(str(Path("templates"))))
    template = env.get_template(Path(designer.get_template_path()).name)
    html = template.render(**ctx)

    # If inline CSS requested but designer uses linked, fetch and inline
    if config.output.inline_css and not designer.get_css() and designer.get_css_url():
        try:
            import requests

            resp = requests.get(designer.get_css_url(), timeout=10)
            resp.raise_for_status()
            # Replace <link> with <style>
            html = html.replace(
                f'<link rel="stylesheet" href="{designer.get_css_url()}">',
                f"<style>{resp.text}</style>",
            )
        except Exception as exc:
            logger.warning("Could not inline CSS: %s", exc)

    html_file = output_dir / f"{config.synthesize.mode}-{edition_date}-{slot}.html"
    html_file.write_text(html, encoding="utf-8")
    return html_file


def _get_slot() -> str:
    """Get time slot from current hour."""
    from datetime import datetime

    hour = datetime.now().hour
    if hour < 12:
        return "morning"
    elif hour < 17:
        return "afternoon"
    else:
        return "evening"

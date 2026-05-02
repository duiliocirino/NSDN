"""Component-based newspaper strategy — V1 implementation."""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

from nsdn.config import AppConfig
from nsdn.db import Database
from nsdn.debug import DebugEmitter
from nsdn.llm import LLMProvider
from nsdn.newspaper.base import NewspaperStrategy
from nsdn.newspaper.cover import CoverDesigner
from nsdn.newspaper.evaluator import Evaluator
from nsdn.newspaper.generator import LayoutGenerator
from nsdn.newspaper.renderer import Renderer
from nsdn.sources.base import FeedEntry

logger = logging.getLogger(__name__)


class DesignedPage:
    """Represents a designed topic page."""

    def __init__(self, html: str, css: str, score: float, topic: str):
        self.html = html
        self.css = css
        self.score = score
        self.topic = topic


class ComponentStrategy(NewspaperStrategy):
    """Component-based newspaper design with iterative VLM feedback."""

    def __init__(
        self,
        config: AppConfig,
        design_llm: LLMProvider,
        evaluate_llm: LLMProvider | None = None,
    ):
        super().__init__(config, design_llm, evaluate_llm)
        from nsdn.newspaper.generator import resolve_fonts

        self.generator = LayoutGenerator(
            design_llm,
            config.newspaper.layouts,
            fonts=resolve_fonts(config.newspaper.font_preset, config.newspaper.fonts or None),
        )
        self.renderer = Renderer({
            "viewport": config.newspaper.viewport,
            "screenshot": config.newspaper.screenshot,
            "pdf": config.newspaper.pdf,
        })
        self.evaluator = Evaluator(
            design_llm,
            evaluate_llm,
            config.newspaper.evaluation,
        )
        self.cover_designer = CoverDesigner(config, self.generator)
        self.emitter: DebugEmitter | None = None

    def run_design(self, db: Database) -> dict[str, Any]:
        """Run the full design pipeline."""
        entries = db.get_kept_entries(processed=False)
        if not entries:
            logger.info("No kept entries to design")
            return {"entries": 0, "topics": 0, "files": []}

        logger.info("Designing %d kept entries", len(entries))

        # Debug emitter
        edition_slug = f"design-{date.today().isoformat()}-{self._get_slot()}"
        output_dir = Path(self.config.output.directory).parent
        self.emitter = DebugEmitter(self.config.debug, output_dir, edition_slug)

        # Step 1: Cluster
        with self.emitter.timer("cluster"):
            entries_by_topic = self._cluster(entries)
        self.emitter.save_json("cluster.json", {t: len(v) for t, v in entries_by_topic.items()})

        if not entries_by_topic:
            return {"entries": len(entries), "topics": 0, "files": []}

        logger.info("Clustered into %d topics: %s", len(entries_by_topic), list(entries_by_topic.keys()))

        # Step 2: Design topic pages (iterative)
        topic_pages: dict[str, DesignedPage] = {}
        for topic, topic_entries in entries_by_topic.items():
            page = self._design_topic(topic_entries, topic)
            topic_pages[topic] = page

        # Step 3: Design cover
        with self.emitter.timer("cover"):
            cover_html, cover_css = self.cover_designer.design(entries_by_topic)
        self.emitter.save_text("cover.html", cover_html)

        # Step 4: Assemble edition
        output_dir = self._setup_output()
        files = self._assemble(output_dir, cover_html, cover_css, topic_pages)

        # Step 5: Mark entries as processed
        guids = [e.guid for e in entries]
        edition_date = date.today().isoformat()
        slot = self._get_slot()
        db.mark_processed(guids, edition_date, slot)

        self.emitter.log_step("complete", topics=len(topic_pages), files=len(files))
        self.emitter.close()
        logger.info("Designed edition: %d topics, %d files", len(topic_pages), len(files))
        return {
            "entries": len(entries),
            "topics": len(topic_pages),
            "files": files,
        }

    def _design_topic(self, entries: list[FeedEntry], topic: str) -> DesignedPage:
        """Design a topic page with iterative feedback."""
        feedback = ""
        best_page = DesignedPage("", "", 0.0, topic)
        max_iterations = self.config.newspaper.max_iterations
        threshold = self.config.newspaper.quality_threshold
        safe_topic = topic.lower().replace(" ", "-").replace("/", "-")

        for iteration in range(max_iterations):
            logger.info("Designing '%s' — iteration %d/%d", topic, iteration + 1, max_iterations)

            # Generate
            with self.emitter.timer("generate", topic=topic, iteration=iteration):
                html, css, layout_spec = self.generator.generate(entries, topic, feedback)
            self.emitter.save_text(f"{safe_topic}/iter{iteration}_spec.json", layout_spec)
            self.emitter.save_text(f"{safe_topic}/iter{iteration}.html", html)

            # Check if HTML is empty — skip eval, force retry
            if not html.strip():
                logger.warning("'%s' iter %d: empty HTML — retrying", topic, iteration)
                feedback = "Generated empty HTML. Produce a valid layout with at least one hero component."
                continue

            # Render screenshot + evaluate
            try:
                screenshot = self.renderer.to_image(html, css)
                self.emitter.save_bytes(f"{safe_topic}/iter{iteration}.png", screenshot)
            except Exception as exc:
                logger.warning("Screenshot failed for '%s': %s — text-only eval", topic, exc)
                score, critique = self.evaluator._evaluate_text(layout_spec)
                score = score * self.evaluator.text_weight / (
                    self.evaluator.text_weight + self.evaluator.vlm_weight
                )
            else:
                score, critique = self.evaluator.evaluate(screenshot, layout_spec, topic)

            self.emitter.log_step(
                "score", topic=topic, iteration=iteration, score=score,
                html_length=len(html), converged=score >= threshold,
            )

            if score > best_page.score:
                best_page = DesignedPage(html, css, score, topic)

            if score >= threshold:
                logger.info("'%s' converged at iteration %d (score: %.1f)", topic, iteration + 1, score)
                return best_page

            feedback = critique
            logger.info("'%s' score: %.1f/%d — continuing", topic, score, threshold)

        logger.warning("'%s' did not converge after %d iterations (best: %.1f)", topic, max_iterations, best_page.score)
        return best_page

    def _cluster(self, entries: list[FeedEntry]) -> dict[str, list[FeedEntry]]:
        """Cluster entries using the configured strategy."""
        from nsdn.clusters import run_cluster
        try:
            return run_cluster(self.config, entries, llm=self.design_llm)
        except Exception as exc:
            logger.error("Clustering failed: %s", exc)
            return {"General": entries}

    def _setup_output(self) -> Path:
        """Create output directory."""
        output_dir = Path(self.config.output.directory)
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _assemble(
        self,
        output_dir: Path,
        cover_html: str,
        cover_css: str,
        topic_pages: dict[str, DesignedPage],
    ) -> list[str]:
        """Assemble edition files.

        Output structure:
            output/journal/{edition_slug}/
                cover.html
                edition.pdf
                topics/
                    {topic}.html
                    {topic}.pdf
        """
        edition_date = date.today().isoformat()
        slot = self._get_slot()
        slug = f"{edition_date}-{slot}"

        # Edition directory
        edition_dir = output_dir / slug
        topics_dir = edition_dir / "topics"
        topics_dir.mkdir(parents=True, exist_ok=True)
        files: list[str] = []

        # Cover
        cover_html_path = edition_dir / "cover.html"
        self._write_page(cover_html_path, cover_html, cover_css)
        files.append(str(cover_html_path))

        # Topic pages
        for topic, page in topic_pages.items():
            safe_topic = topic.lower().replace(" ", "-").replace("/", "-")
            topic_html_path = topics_dir / f"{safe_topic}.html"
            self._write_page(topic_html_path, page.html, page.css)
            files.append(str(topic_html_path))

            try:
                topic_pdf_path = topics_dir / f"{safe_topic}.pdf"
                pdf_bytes = self.renderer.to_pdf(page.html, page.css)
                topic_pdf_path.write_bytes(pdf_bytes)
                files.append(str(topic_pdf_path))
            except Exception as exc:
                logger.warning("PDF failed for '%s': %s", topic, exc)

        # Combined edition PDF
        try:
            all_html, all_css = self._combine_pages(cover_html, cover_css, topic_pages)
            edition_pdf_path = edition_dir / "edition.pdf"
            edition_pdf_bytes = self.renderer.to_pdf(all_html, all_css)
            edition_pdf_path.write_bytes(edition_pdf_bytes)
            files.append(str(edition_pdf_path))
        except Exception as exc:
            logger.warning("Edition PDF failed: %s", exc)

        return files

    @staticmethod
    def _write_page(path: Path, html: str, css: str) -> None:
        """Write a complete HTML page."""
        combined = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>{css}</style>
</head>
<body>
{html}
</body>
</html>
"""
        path.write_text(combined, encoding="utf-8")

    @staticmethod
    def _combine_pages(
        cover_html: str,
        cover_css: str,
        topic_pages: dict[str, DesignedPage],
    ) -> tuple[str, str]:
        """Combine all pages into one document for PDF. Returns (html, merged_css)."""
        html_parts = [cover_html]
        css_set: set[str] = {cover_css}  # deduplicate CSS blocks

        for topic, page in topic_pages.items():
            html_parts.append('<div style="page-break-before: always"></div>')
            html_parts.append(page.html)
            css_set.add(page.css)

        return "\n".join(html_parts), "\n".join(css_set)

    @staticmethod
    def _get_slot() -> str:
        """Get time slot from current hour."""
        hour = datetime.now().hour
        if hour < 12:
            return "morning"
        elif hour < 17:
            return "afternoon"
        else:
            return "evening"


# Auto-register
from nsdn.newspaper import register_newspaper
register_newspaper("component", ComponentStrategy)

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
            colors=config.newspaper.colors or None,
            viewport_modes=config.newspaper.modes,
        )
        self.renderer = Renderer(
            {
                "viewport": config.newspaper.viewport,
                "screenshot": config.newspaper.screenshot,
                "pdf": config.newspaper.pdf,
            },
            viewport_modes=config.newspaper.modes,
        )
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
            return {"entries": 0, "topics": 0, "files": [], "edition_dir": ""}

        logger.info("Designing %d kept entries", len(entries))

        # Debug emitter
        edition_slug = f"design-{date.today().isoformat()}-{self._get_slot()}"
        output_dir = Path(self.config.output.directory).parent
        self.emitter = DebugEmitter(self.config.debug, output_dir, edition_slug)

        try:
            # Step 1: Cluster
            with self.emitter.timer("cluster"):
                entries_by_topic = self._cluster(entries)
            self.emitter.save_json("cluster.json", {t: len(v) for t, v in entries_by_topic.items()})

            if not entries_by_topic:
                return {"entries": len(entries), "topics": 0, "files": [], "edition_dir": ""}

            logger.info("Clustered into %d topics: %s", len(entries_by_topic), list(entries_by_topic.keys()))

            # Step 2: Design topic pages (iterative, desktop + mobile)
            topic_pages: dict[str, tuple[DesignedPage, DesignedPage]] = {}
            for topic, topic_entries in entries_by_topic.items():
                desktop_page, mobile_page = self._design_topic(topic_entries, topic)
                topic_pages[topic] = (desktop_page, mobile_page)

            # Step 3: Design cover (desktop + mobile)
            with self.emitter.timer("cover"):
                cover_html, cover_css = self.cover_designer.design(entries_by_topic)
            self.emitter.save_text("cover.html", cover_html)

            generate_mobile = self.config.newspaper.generate_mobile
            self._mobile_cover_html = ""
            self._mobile_cover_css = ""
            if generate_mobile:
                with self.emitter.timer("cover-mobile"):
                    self._mobile_cover_html, self._mobile_cover_css = self.generator.generate_cover(
                        self.cover_designer._get_selector().select(entries_by_topic),
                        entries_by_topic,
                        date.today().isoformat(),
                        self._get_slot(),
                        mode="mobile",
                    )
                self.emitter.save_text("cover-mobile.html", self._mobile_cover_html)

            # Step 4: Assemble edition
            output_dir = self._setup_output()
            files = self._assemble(output_dir, cover_html, cover_css, topic_pages)

            # Step 5: Mark entries as processed + record edition
            guids = [e.guid for e in entries]
            edition_date = date.today().isoformat()
            slot = self._get_slot()
            db.mark_processed(guids, edition_date, slot)
            # Record in editions table so the UI can find it
            # Note: edition dir is {date}-{slot}, not design-{date}-{slot}
            edition_dir = output_dir / f"{edition_date}-{slot}"
            cover_path = str(edition_dir / "cover.html")
            edition_pdf = str(edition_dir / "edition.pdf")
            db.record_edition(edition_date, slot, cover_path, edition_pdf, len(entries))

            self.emitter.log_step("complete", topics=len(topic_pages), files=len(files))
            logger.info("Designed edition: %d topics, %d files", len(topic_pages), len(files))
            return {
                "entries": len(entries),
                "topics": len(topic_pages),
                "files": files,
                "edition_dir": str(edition_dir),
            }
        finally:
            self.emitter.close()

    def _design_topic(self, entries: list[FeedEntry], topic: str) -> tuple[DesignedPage, DesignedPage]:
        """Design a topic page for desktop + mobile with iterative feedback.

        Returns (desktop_page, mobile_page).
        Layout spec is generated ONCE per iteration, then rendered for both modes.
        """
        feedback = ""
        best_desktop = DesignedPage("", "", 0.0, topic)
        best_mobile = DesignedPage("", "", 0.0, topic)
        max_iterations = self.config.newspaper.max_iterations
        threshold = self.config.newspaper.quality_threshold
        eval_modes = self.config.newspaper.eval_modes
        generate_mobile = self.config.newspaper.generate_mobile
        safe_topic = topic.lower().replace(" ", "-").replace("/", "-")

        for iteration in range(max_iterations):
            logger.info("Designing '%s' — iteration %d/%d", topic, iteration + 1, max_iterations)

            # Clear cache so LLM generates fresh spec with feedback
            self.generator.clear_cache()

            # Generate desktop (invokes LLM, caches spec)
            with self.emitter.timer("generate", topic=topic, iteration=iteration):
                desktop_html, desktop_css, layout_spec = self.generator.generate(entries, topic, feedback)
            self.emitter.save_text(f"{safe_topic}/iter{iteration}_spec.json", layout_spec)
            self.emitter.save_text(f"{safe_topic}/iter{iteration}.html", desktop_html)

            # Check if HTML is empty — skip eval, force retry
            if not desktop_html.strip():
                logger.warning("'%s' iter %d: empty HTML — retrying", topic, iteration)
                feedback = "Generated empty HTML. Produce a valid layout with at least one hero component."
                continue

            # Generate mobile from cached spec (no LLM call)
            if generate_mobile:
                mobile_html, mobile_css, _ = self.generator.generate_mode(
                    entries, topic, feedback, mode="mobile"
                )
                self.emitter.save_text(f"{safe_topic}/iter{iteration}-mobile.html", mobile_html)
            else:
                mobile_html = mobile_css = ""

            # Evaluate desktop
            desktop_score, desktop_critique = self._evaluate_mode(
                desktop_html, desktop_css, layout_spec, topic, "desktop"
            )

            # Evaluate mobile
            if generate_mobile and eval_modes == "full":
                mobile_score, mobile_critique = self._evaluate_mode(
                    mobile_html, mobile_css, layout_spec, topic, "mobile"
                )
            elif generate_mobile:
                # Fast path: reuse desktop score
                mobile_score, mobile_critique = desktop_score, desktop_critique
            else:
                mobile_score, mobile_critique = 0.0, ""

            self.emitter.log_step(
                "score", topic=topic, iteration=iteration,
                desktop_score=desktop_score, mobile_score=mobile_score,
                converged=(desktop_score >= threshold and mobile_score >= threshold),
            )

            if desktop_score > best_desktop.score:
                best_desktop = DesignedPage(desktop_html, desktop_css, desktop_score, topic)

            if generate_mobile and mobile_score > best_mobile.score:
                best_mobile = DesignedPage(mobile_html, mobile_css, mobile_score, topic)

            # Convergence check
            if desktop_score >= threshold and (not generate_mobile or mobile_score >= threshold):
                logger.info(
                    "'%s' converged at iteration %d (desktop: %.1f, mobile: %.1f)",
                    topic, iteration + 1, desktop_score, mobile_score,
                )
                return best_desktop, best_mobile

            # Combined feedback for next iteration
            feedback = "\n\n".join(filter(None, [desktop_critique, mobile_critique]))
            logger.info(
                "'%s' desktop: %.1f mobile: %.1f / %d — continuing",
                topic, desktop_score, mobile_score, threshold,
            )

        logger.warning(
            "'%s' did not converge after %d iterations (desktop: %.1f, mobile: %.1f)",
            topic, max_iterations, best_desktop.score, best_mobile.score,
        )
        return best_desktop, best_mobile

    def _evaluate_mode(
        self,
        html: str,
        css: str,
        layout_spec: str,
        topic: str,
        mode: str,
    ) -> tuple[float, str]:
        """Render PDF, convert pages to images, evaluate all pages."""
        safe_topic = topic.lower().replace(" ", "-").replace("/", "-")
        try:
            pdf_bytes = self.renderer.to_pdf(html, css, topic, mode=mode)
            page_images = self.renderer.pdf_to_images(pdf_bytes)
            for i, img in enumerate(page_images):
                self.emitter.save_bytes(f"{safe_topic}/{mode}-page{i}.png", img)
        except Exception as exc:
            logger.warning("PDF render failed for '%s' (%s): %s — text-only eval", topic, mode, exc)
            score, critique = self.evaluator._evaluate_text(layout_spec)
            score = score * self.evaluator.text_weight / (
                self.evaluator.text_weight + self.evaluator.vlm_weight
            )
            return score, critique

        if len(page_images) == 1:
            score, critique = self.evaluator.evaluate(page_images[0], layout_spec, topic)
        else:
            score, critique = self.evaluator.evaluate_multipage(page_images, layout_spec, topic)
        return score, critique

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
        topic_pages: dict[str, tuple[DesignedPage, DesignedPage]],
    ) -> list[str]:
        """Assemble edition files for desktop + mobile.

        Output structure:
            output/journal/{edition_slug}/
                cover.html
                edition.pdf            (desktop combined)
                edition-mobile.pdf    (mobile combined)
                topics/
                    {topic}.html      (desktop)
                    {topic}.pdf       (desktop)
                    {topic}-mobile.html
                    {topic}-mobile.pdf
        """
        edition_date = date.today().isoformat()
        slot = self._get_slot()
        slug = f"{edition_date}-{slot}"
        generate_mobile = self.config.newspaper.generate_mobile

        edition_dir = output_dir / slug
        topics_dir = edition_dir / "topics"
        topics_dir.mkdir(parents=True, exist_ok=True)
        files: list[str] = []

        # Cover
        cover_html_path = edition_dir / "cover.html"
        self._write_page(cover_html_path, cover_html, cover_css)
        files.append(str(cover_html_path))

        # Topic pages — desktop + mobile
        for topic, (desktop_page, mobile_page) in topic_pages.items():
            safe_topic = topic.lower().replace(" ", "-").replace("/", "-")

            # Desktop
            topic_html_path = topics_dir / f"{safe_topic}.html"
            self._write_page(topic_html_path, desktop_page.html, desktop_page.css, topic)
            files.append(str(topic_html_path))

            try:
                topic_pdf_path = topics_dir / f"{safe_topic}.pdf"
                pdf_bytes = self.renderer.to_pdf(desktop_page.html, desktop_page.css, topic)
                topic_pdf_path.write_bytes(pdf_bytes)
                files.append(str(topic_pdf_path))
            except Exception as exc:
                logger.warning("PDF failed for '%s' (desktop): %s", topic, exc)

            # Mobile
            if generate_mobile and mobile_page.html:
                mobile_html_path = topics_dir / f"{safe_topic}-mobile.html"
                self._write_page(mobile_html_path, mobile_page.html, mobile_page.css, topic)
                files.append(str(mobile_html_path))

                try:
                    mobile_pdf_path = topics_dir / f"{safe_topic}-mobile.pdf"
                    mobile_pdf_bytes = self.renderer.to_pdf(mobile_page.html, mobile_page.css, topic, mode="mobile")
                    mobile_pdf_path.write_bytes(mobile_pdf_bytes)
                    files.append(str(mobile_pdf_path))
                except Exception as exc:
                    logger.warning("PDF failed for '%s' (mobile): %s", topic, exc)

        # Combined edition PDFs
        try:
            desktop_pages = {t: dp for t, (dp, _) in topic_pages.items()}
            all_html, all_css = self._combine_pages(cover_html, cover_css, desktop_pages)
            edition_pdf_path = edition_dir / "edition.pdf"
            edition_pdf_bytes = self.renderer.to_pdf(all_html, all_css, mode="desktop")
            edition_pdf_path.write_bytes(edition_pdf_bytes)
            files.append(str(edition_pdf_path))
        except Exception as exc:
            logger.warning("Edition PDF (desktop) failed: %s", exc)

        if generate_mobile:
            try:
                mobile_pages = {t: mp for t, (_, mp) in topic_pages.items() if mp.html}
                if mobile_pages:
                    # Use mobile cover if available, else generate one
                    if hasattr(self, "_mobile_cover_html") and self._mobile_cover_html:
                        m_cover_html = self._mobile_cover_html
                        m_cover_css = self._mobile_cover_css
                    else:
                        m_cover_html = cover_html
                        m_cover_css = cover_css
                    mobile_html, mobile_css = self._combine_pages(m_cover_html, m_cover_css, mobile_pages)
                    mobile_edition_pdf = edition_dir / "edition-mobile.pdf"
                    mobile_pdf_bytes = self.renderer.to_pdf(mobile_html, mobile_css, mode="mobile")
                    mobile_edition_pdf.write_bytes(mobile_pdf_bytes)
                    files.append(str(mobile_edition_pdf))
            except Exception as exc:
                logger.warning("Edition PDF (mobile) failed: %s", exc)

        return files

    @staticmethod
    def _write_page(path: Path, html: str, css: str, topic: str | None = None) -> None:
        """Write a complete HTML page."""
        topic_header = ""
        if topic:
            topic_header = f'<header class="topic-header"><h1>{topic}</h1></header>'
        combined = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>{css}</style>
</head>
<body>
{topic_header}
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
            html_parts.append(f'<header class="topic-header"><h1>{topic}</h1></header>')
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

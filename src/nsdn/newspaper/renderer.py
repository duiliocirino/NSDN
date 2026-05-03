"""Renderer — HTML → screenshot (Playwright) and HTML → PDF (WeasyPrint)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class Renderer:
    """Renders HTML to screenshots and PDFs."""

    # A4 at 96dpi ≈ 794x1123px; printable area with ~20mm margins ≈ 644x973px
    A4_WIDTH = 794

    def __init__(self, config: dict):
        self.viewport = config.get("viewport", {"width": self.A4_WIDTH, "height": 1123})
        self.screenshot_config = config.get("screenshot", {"dpi": 300})
        self.pdf_config = config.get("pdf", {"format": "A4", "margin": "20mm"})
        self._browser = None

    def to_image(self, html: str, css: str, topic: str | None = None) -> bytes:
        """Render HTML to screenshot via Playwright (sync wrapper).

        Uses asyncio.run() to wrap async Playwright calls.
        """
        combined = self._combine_html_css(html, css, topic)
        return asyncio.run(self._to_image_async(combined))

    async def _to_image_async(self, combined_html: str) -> bytes:
        """Async Playwright screenshot."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError("Install playwright: poetry add playwright && playwright install chromium")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(
                viewport={"width": self.viewport["width"], "height": self.viewport["height"]}
            )
            # Write to temp file for reliable loading
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
                f.write(combined_html)
                f.flush()
                tmp_path = f.name
            try:
                await page.goto(f"file://{tmp_path}", wait_until="networkidle")
                screenshot = await page.screenshot(type="png", scale="device")
            finally:
                Path(tmp_path).unlink(missing_ok=True)
            await browser.close()
            return screenshot

    def to_pdf(self, html: str, css: str, topic: str | None = None) -> bytes:
        """Render HTML to PDF via WeasyPrint."""
        try:
            from weasyprint import HTML
        except ImportError:
            raise ImportError("Install weasyprint: poetry add weasyprint")

        combined = self._combine_html_css(html, css, topic)
        doc = HTML(string=combined)
        margin = self.pdf_config.get("margin", "20mm")
        format_size = self.pdf_config.get("format", "A4")
        # Use @page for margins, not * { padding } which inflates every element
        # Allow high-res images (WeasyPrint defaults to 300dpi, we want full resolution)
        pdf_bytes = doc.write_pdf(
            presentation={
                "@page": {
                    "size": format_size,
                    "margin": margin,
                },
            },
            maximum_reserved_images=20,  # Allow more images in cache
        )
        if pdf_bytes is None:
            raise ValueError("PDF generation failed")
        return pdf_bytes

    def to_string(self, html: str, css: str) -> str:
        """Return combined HTML string for text review."""
        return self._combine_html_css(html, css)

    @staticmethod
    def _combine_html_css(html: str, css: str, topic: str | None = None) -> str:
        """Combine HTML and CSS into a single document."""
        topic_header = ""
        if topic:
            topic_header = f'<header class="topic-header"><h2>{topic}</h2></header>'
        return f"""<!DOCTYPE html>
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

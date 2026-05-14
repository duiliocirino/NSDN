"""Renderer — HTML → screenshot (Playwright) and HTML → PDF (WeasyPrint)."""

from __future__ import annotations

import asyncio
import logging
from io import BytesIO
from pathlib import Path

logger = logging.getLogger(__name__)

# Silence noisy PDF/rendering libraries
logging.getLogger("fontTools").setLevel(logging.WARNING)
logging.getLogger("weasyprint").setLevel(logging.WARNING)


class Renderer:
    """Renders HTML to screenshots and PDFs."""

    # A4 at 96dpi ≈ 794x1123px; printable area with ~20mm margins ≈ 644x973px
    A4_WIDTH = 794

    def __init__(self, config: dict, viewport_modes: dict | None = None):
        self.viewport = config.get("viewport", {"width": self.A4_WIDTH, "height": 1123})
        self.screenshot_config = config.get("screenshot", {"dpi": 300})
        self.pdf_config = config.get("pdf", {"format": "A4", "margin": "20mm"})
        self.viewport_modes = viewport_modes or {}
        self._browser = None

    def _get_viewport(self, mode: str) -> dict:
        """Get viewport dimensions for a rendering mode."""
        if mode in self.viewport_modes:
            return self.viewport_modes[mode].viewport
        return self.viewport

    def _get_format(self, mode: str) -> str:
        """Get @page size for a rendering mode."""
        if mode == "mobile" and "mobile" in self.viewport_modes:
            vp = self.viewport_modes["mobile"].viewport
            return f"{vp['width']}px {vp['height']}px"
        return self.pdf_config.get("format", "A4")

    def to_image(self, html: str, css: str, topic: str | None = None, mode: str = "desktop") -> bytes:
        """Render HTML to screenshot via Playwright (sync wrapper).

        Uses asyncio.run() to wrap async Playwright calls.
        """
        combined = self._combine_html_css(html, css, topic)
        viewport = self._get_viewport(mode)
        return asyncio.run(self._to_image_async(combined, viewport))

    async def _to_image_async(self, combined_html: str, viewport: dict) -> bytes:
        """Async Playwright screenshot."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError("Install playwright: poetry add playwright && playwright install chromium")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(
                viewport={"width": viewport["width"], "height": viewport["height"]}
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

    def to_pdf(self, html: str, css: str, topic: str | None = None, mode: str = "desktop") -> bytes:
        """Render HTML to PDF via WeasyPrint."""
        try:
            from weasyprint import CSS, HTML
        except ImportError:
            raise ImportError("Install weasyprint: poetry add weasyprint")

        combined = self._combine_html_css(html, css, topic)
        doc = HTML(string=combined)
        format_size = self._get_format(mode)
        # @page rule with zero margin via separate stylesheet (matching screenshot viewport)
        # Allow high-res images (WeasyPrint defaults to 300dpi, we want full resolution)
        page_stylesheet = CSS(string=self._page_css(format_size))
        pdf_bytes = doc.write_pdf(stylesheets=[page_stylesheet])
        if pdf_bytes is None:
            raise ValueError("PDF generation failed")
        return pdf_bytes

    @staticmethod
    def _page_css(format_size: str) -> str:
        """Generate @page rule for PDF — zero margin to match screenshot."""
        return f"@page {{ size: {format_size}; margin: 0; }}"

    def to_string(self, html: str, css: str) -> str:
        """Return combined HTML string for text review."""
        return self._combine_html_css(html, css)

    def pdf_to_images(self, pdf_bytes: bytes, dpi: int = 200) -> list[bytes]:
        """Convert PDF pages to PNG images.

        Returns a list of PNG bytes, one per page.
        """
        try:
            import pypdfium2 as pdfium
        except ImportError:
            raise ImportError("Install pypdfium2: poetry add pypdfium2")

        doc = pdfium.PdfDocument(BytesIO(pdf_bytes))
        result: list[bytes] = []
        for page in doc:
            scale = dpi / 72
            bitmap = page.render(scale=scale, rotation=0)
            pil_image = bitmap.to_pil()
            buf = BytesIO()
            pil_image.save(buf, format="PNG")
            result.append(buf.getvalue())
        doc.close()
        return result

    @staticmethod
    def _combine_html_css(html: str, css: str, topic: str | None = None) -> str:
        """Combine HTML and CSS into a single document."""
        topic_header = ""
        if topic:
            topic_header = f'<header class="topic-header"><h1>{topic}</h1></header>'
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

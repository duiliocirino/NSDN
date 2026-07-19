"""Render pipeline — Markdown → HTML with designer support."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import requests

from nsdn.config import AppConfig
from nsdn.designers import get_designer

logger = logging.getLogger(__name__)


def render_markdown(config: AppConfig, md_path: Path) -> Path:
    """Render a Markdown file to HTML using the configured designer."""
    import mistune
    from jinja2 import Environment, FileSystemLoader

    md_content = md_path.read_text(encoding="utf-8")
    html_body = mistune.html(md_content)

    # Parse edition date and slot from filename
    stem = md_path.stem  # e.g. "2025-01-15-morning"
    parts = stem.rsplit("-", 1)
    if len(parts) == 2:
        edition_date, slot = parts
    else:
        edition_date, slot = stem, "default"

    designer_class = get_designer(config.output.designer)
    designer = designer_class(config.output.model_dump())
    ctx = designer.get_context(html_body, edition_date, slot)

    env = Environment(loader=FileSystemLoader(str(Path("templates"))))
    template = env.get_template(Path(designer.get_template_path()).name)
    html = template.render(**ctx)

    # Handle inline CSS
    if config.output.inline_css and not designer.get_css() and designer.get_css_url():
        try:
            resp = requests.get(designer.get_css_url(), timeout=10)
            resp.raise_for_status()
            html = html.replace(
                f'<link rel="stylesheet" href="{designer.get_css_url()}">',
                f"<style>{resp.text}</style>",
            )
        except Exception as exc:
            logger.warning("Could not inline CSS: %s", exc)

    # Handle image caching
    if config.output.cache_images:
        html = _cache_images(config, html, md_path.parent)

    html_file = md_path.with_suffix(".html")
    html_file.write_text(html, encoding="utf-8")
    logger.info("Rendered %s → %s", md_path, html_file)
    return html_file


def _cache_images(config: AppConfig, html: str, output_dir: Path) -> str:
    """Download remote images to assets/ and update HTML references."""
    import re

    assets_dir = output_dir.parent / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    # Find all img tags with src URLs
    def download_image(match: re.Match) -> str:
        url = match.group(1)
        if url.startswith(("http:", "https:")):
            try:
                resp = requests.get(url, timeout=15)
                resp.raise_for_status()
                # Hash-based filename for dedup
                ext = Path(url).suffix.split("?")[0] or ".jpg"
                filename = hashlib.md5(url.encode()).hexdigest()[:12] + ext
                filepath = assets_dir / filename
                filepath.write_bytes(resp.content)
                return f'<img src="assets/{filename}" alt="{match.group(2)}">'
            except Exception as exc:
                logger.warning("Failed to cache image %s: %s", url, exc)
                return match.group(0)
        return match.group(0)

    # Match <img src="..." alt="...">
    pattern = r'<img src="(https?://[^"]+)" alt="([^"]*)">'
    html = re.sub(pattern, download_image, html)

    return html


def render_directory(config: AppConfig, output_dir: str | None = None) -> list[Path]:
    """Render all .md files in the output directory."""
    dir_path = Path(output_dir or config.output.directory)
    md_files = sorted(dir_path.glob("*.md"))
    rendered: list[Path] = []

    if not md_files:
        logger.info("No Markdown files to render in %s", dir_path)
        return rendered

    for md_file in md_files:
        # Skip if HTML already exists
        html_file = md_file.with_suffix(".html")
        if html_file.exists():
            continue
        rendered.append(render_markdown(config, md_file))

    return rendered

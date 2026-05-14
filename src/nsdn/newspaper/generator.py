"""LayoutGenerator — composes HTML/CSS from layout elements."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from nsdn.llm import LLMProvider
from nsdn.newspaper import prompts
from nsdn.newspaper.layouts import hero, grid, sidebar
from nsdn.sources.base import FeedEntry

logger = logging.getLogger(__name__)


def _strip_image_urls(text: str) -> str:
    """Remove image URLs that may have leaked into summary text."""
    # Remove lines that are just image URLs (redd.it, i.redd.it, etc.)
    lines = text.split("\n")
    clean = [l for l in lines if not re.search(r'https?://\S*\.(png|jpg|jpeg|webp)', l.strip())]
    return " ".join(l.strip() for l in clean if l.strip())

def resolve_image_url(url: str) -> str | None:
    """Resolve image URL to highest available resolution.

    Only Reddit-hosted images are used. All other domains are rejected
    to avoid ghost images (broken links showing only alt text in a border).

    preview.redd.it / external-preview.redd.it -> i.redd.it (full-res).
    """
    if not url:
        return None
    base = url.split("?")[0].replace("&amp;", "&")
    if "i.redd.it/" in base:
        return base
    if "preview.redd.it/" in base or "external-preview.redd.it/" in base:
        base = base.replace("https://preview.redd.it/", "https://i.redd.it/")
        base = base.replace("https://external-preview.redd.it/", "https://i.redd.it/")
        return base
    return None

# Font presets — name → (serif, sans, google_fonts)
FONT_PRESETS: dict[str, tuple[str, str, str]] = {
    "classic": (
        "Georgia, 'Times New Roman', serif",
        "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        "",
    ),
    "editorial": (
        "'Playfair Display', Georgia, serif",
        "'Source Sans Pro', sans-serif",
        "https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700&family=Source+Sans+Pro:wght@400;600&display=swap",
    ),
    "modern": (
        "'Inter', Georgia, serif",
        "'Inter', sans-serif",
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap",
    ),
    "newspaper": (
        "'Times New Roman', serif",
        "Helvetica, Arial, sans-serif",
        "",
    ),
}


def resolve_fonts(preset: str = "classic", overrides: dict[str, str] | None = None) -> dict[str, str]:
    """Resolve a font preset name to a fonts dict, applying custom overrides."""
    if preset not in FONT_PRESETS:
        logger.warning("Unknown font preset '%s', falling back to 'classic'", preset)
        preset = "classic"
    serif, sans, google = FONT_PRESETS[preset]
    result = {"serif": serif, "sans": sans, "google_fonts": google}
    if overrides:
        result.update(overrides)
    return result

LAYOUT_MODULES = {
    "hero": hero,
    "grid": grid,
    "sidebar": sidebar,
}


class LayoutGenerator:
    """Generates HTML/CSS from LLM layout specs."""

    def __init__(
        self,
        llm: LLMProvider,
        enabled_layouts: list[str] | None = None,
        fonts: dict[str, str] | None = None,
        colors: dict[str, str] | None = None,
        viewport_modes: dict[str, Any] | None = None,
    ):
        self.llm = llm
        self.enabled_layouts = enabled_layouts or list(LAYOUT_MODULES.keys())
        self.fonts = fonts or {
            "serif": "Georgia, 'Times New Roman', serif",
            "sans": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            "google_fonts": "",
        }
        self.colors = colors or {
            "text": "#333",
            "text-muted": "#555",
            "border": "#333",
            "border-light": "#eee",
            "accent": "#0066cc",
        }
        self._viewport_modes = viewport_modes or {}
        self._entries: dict[str, dict[str, Any]] = {}

    def generate(self, entries: list[FeedEntry], topic: str, feedback: str = "") -> tuple[str, str, str]:
        """Generate layout spec via LLM, render desktop HTML/CSS.

        Returns:
            (html, css, layout_spec_json)
        """
        return self.generate_mode(entries, topic, feedback, mode="desktop")

    def generate_mode(self, entries: list[FeedEntry], topic: str, feedback: str = "", mode: str = "desktop") -> tuple[str, str, str]:
        """Generate layout spec via LLM, render for a specific viewport mode.

        On first call (any mode), the LLM is invoked once to produce the layout spec.
        Subsequent calls for other modes reuse the cached spec and just re-render.

        Returns:
            (html, css, layout_spec_json)
        """
        self._entries = {
            e.guid: {
                "guid": e.guid,
                "title": e.title,
                "summary": e.summary or "",
                "link": e.link or "",
                "score": e.score,
                "image_url": resolve_image_url(e.images[0]) if e.images else None,
            }
            for e in entries
        }

        # Cache: invoke LLM only once per generate cycle
        if not hasattr(self, "_cached_layout_spec"):
            entry_dicts = list(self._entries.values())
            user_prompt = prompts.build_design_prompt(topic, entry_dicts, feedback)
            spec_text = self.llm.invoke(user_prompt, system_message=prompts.DESIGN_SYSTEM_PROMPT, temperature=0.7)
            self._cached_layout_spec = self._parse_spec(spec_text)

        layout_spec = self._cached_layout_spec
        html, css = self._render(layout_spec, mode=mode)
        return html, css, json.dumps(layout_spec, indent=2)

    def clear_cache(self) -> None:
        """Clear the cached layout spec (call between topics)."""
        if hasattr(self, "_cached_layout_spec"):
            delattr(self, "_cached_layout_spec")

    def generate_cover(self, highlights: list[FeedEntry], entries_by_topic: dict[str, list[FeedEntry]], date: str, slot: str, mode: str = "desktop") -> tuple[str, str]:
        """Generate cover page HTML/CSS for a specific viewport mode."""
        columns = 2 if mode == "desktop" else 1
        html_parts: list[str] = []
        html_parts.append(f"""
        <header class="cover-header">
            <h1>NSDN</h1>
            <p class="date">{date} — {slot}</p>
        </header>
        """)

        if highlights:
            best = max(highlights, key=lambda e: e.score)
            html_parts.append(hero.render({
                "title": best.title,
                "summary": best.summary or "",
                "link": best.link or "",
            }, mode=mode))
        else:
            raise NotImplementedError("No highlights for cover design")

        remaining = [h for h in highlights if h.guid != best.guid]
        if remaining:
            entry_dicts = [
                {"title": e.title, "summary": e.summary or "", "link": e.link or ""}
                for e in remaining
            ]
            html_parts.append(grid.render(entry_dicts, columns=columns, mode=mode))

        all_css = "\n".join([hero.css(), grid.css(), COVER_CSS])
        return "\n".join(html_parts), all_css

    @staticmethod
    def _entry_to_dict(entry: dict[str, Any]) -> dict[str, Any]:
        """Convert internal entry dict to component-ready dict, sanitizing summary."""
        summary = entry.get("summary", "")
        # Strip image URLs that the LLM may have leaked into summary
        summary = _strip_image_urls(summary)
        return {
            "title": entry.get("title", ""),
            "summary": summary,
            "link": entry.get("link", ""),
            "image_url": entry.get("image_url"),
        }

    def _parse_spec(self, text: str) -> dict[str, Any]:
        """Parse LLM response into layout spec."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        if "```" in text:
            for block in text.split("```"):
                block = block.strip()
                if block.startswith("json"):
                    block = block[4:].strip()
                try:
                    return json.loads(block)
                except json.JSONDecodeError:
                    continue
        logger.warning("Could not parse layout spec, using fallback")
        return {"layout": {"components": [], "style": {}}}

    def _render(self, spec: dict[str, Any], mode: str = "desktop") -> tuple[str, str]:
        """Render layout spec to HTML/CSS for a given viewport mode."""
        layout = spec.get("layout", {})
        components = layout.get("components", [])
        style = layout.get("style", {})
        
        # Get viewport config for this mode
        viewport_cfg = {}
        if hasattr(self, "_viewport_modes") and mode in self._viewport_modes:
            vp = self._viewport_modes[mode]
            viewport_cfg = {
                "base_font_size": vp.base_font_size,
                "container_width": f"{vp.viewport['width']}px",
                "spacing": vp.spacing,
            }
        
        html_parts: list[str] = []
        css_parts: list[str] = [_build_base_css(self.fonts, self.colors, mode, viewport_cfg)]
        columns = style.get("columns", 2)
        if mode == "mobile":
            columns = 1  # Force single column for mobile

        for comp in components:
            # Normalize: LLM may send "Hero", "Grid", etc.
            comp_type = comp.get("type", "").lower()
            module = LAYOUT_MODULES.get(comp_type)
            if not module:
                logger.debug("Skipping unknown component type: %s", comp.get("type"))
                continue

            if comp_type == "hero":
                guid = comp.get("entry_guid") or comp.get("guid")
                if guid and guid in self._entries:
                    html_parts.append(module.render(self._entry_to_dict(self._entries[guid]), mode=mode))
                    css_parts.append(module.css())
                else:
                    logger.warning("Hero component: no entry found for guid=%s", guid)

            elif comp_type == "grid":
                guids = comp.get("entry_guids") or comp.get("guids", [])
                if not guids and "guid" in comp:
                    guids = [comp["guid"]]
                if not isinstance(guids, list):
                    guids = [guids]
                entries = [self._entries[g] for g in guids if g in self._entries]
                if entries:
                    entry_dicts = [self._entry_to_dict(e) for e in entries]
                    html_parts.append(module.render(entry_dicts, columns=columns, mode=mode))
                    css_parts.append(module.css())

            elif comp_type == "sidebar":
                guids = comp.get("entry_guids") or comp.get("guids", [])
                if not guids and "guid" in comp:
                    guids = [comp["guid"]]
                if not isinstance(guids, list):
                    guids = [guids]
                entries = [self._entries[g] for g in guids if g in self._entries]
                if entries:
                    entry_dicts = [self._entry_to_dict(e) for e in entries]
                    html_parts.append(module.render(entry_dicts, mode=mode))
                    css_parts.append(module.css())

        return "\n".join(html_parts), "\n".join(css_parts)


def _build_base_css(
    fonts: dict[str, str],
    colors: dict[str, str] | None = None,
    mode: str = "desktop",
    viewport_cfg: dict | None = None,
) -> str:
    """Generate base CSS with configurable fonts, colors, and viewport mode."""
    colors = colors or {
        "text": "#333",
        "text-muted": "#555",
        "border": "#333",
        "border-light": "#eee",
        "accent": "#0066cc",
    }
    viewport_cfg = viewport_cfg or {}
    base_font = viewport_cfg.get("base_font_size", "0.85rem")
    container_width = viewport_cfg.get("container_width", "800px")
    spacing = viewport_cfg.get("spacing", "1.5rem")
    google_import = f"@import url('{fonts['google_fonts']}');" if fonts.get("google_fonts") else ""
    return f"""
{google_import}
:root {{
    --color-text: {colors["text"]};
    --color-text-muted: {colors["text-muted"]};
    --color-border: {colors["border"]};
    --color-border-light: {colors["border-light"]};
    --color-accent: {colors["accent"]};
    --font-serif: {fonts["serif"]};
    --font-sans: {fonts["sans"]};
}}
body {{
    max-width: {container_width};
    margin: 0 auto;
    padding: {spacing};
    font-family: var(--font-serif);
    font-size: {base_font};
    line-height: 1.5;
    color: var(--color-text);
}}
.topic-header {{
    text-align: center;
    margin: 2.5rem 0 2rem;
    padding: 1.5rem 0 1.5rem;
    border-top: 3px solid var(--color-accent);
    border-bottom: 1px solid var(--color-border-light);
}}
.topic-header h1 {{
    font-size: 2rem;
    font-family: var(--font-serif);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin: 0;
    color: var(--color-text);
    line-height: 1.1;
}}
.source-link {{
    font-size: 0.75rem;
    color: var(--color-accent);
    text-decoration: none;
}}
.source-link:hover {{
    text-decoration: underline;
}}
"""

COVER_CSS = """
.cover-header {
    text-align: center;
    border-bottom: 3px double var(--color-border);
    padding-bottom: 1.5rem;
    margin-bottom: 2rem;
}
.cover-header h1 {
    font-size: 2rem;
    letter-spacing: 0.1em;
    margin-bottom: 0.4rem;
}
.cover-header .date {
    font-size: 0.85rem;
    color: var(--color-text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
"""

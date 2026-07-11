"""Grid layout — multi-column article list."""

from __future__ import annotations


def render(entries: list[dict], columns: int = 2, mode: str = "desktop", css_vars: dict | None = None) -> str:
    """Render a grid of articles — newspaper-style floated thumbnails.
    
    Desktop: floated thumbnails, multi-column
    Mobile: stacked thumbnails, single column
    """
    css_vars = css_vars or {}
    items = ""
    for entry in entries:
        source_html = f'<a href="{entry["link"]}" class="source-link" target="_blank" rel="noopener">Source ↗</a>' if entry.get("link") else ""
        image_html = ''
        if entry.get("image_url"):
            if mode == "mobile":
                image_html = f'<img class="grid-thumb grid-thumb--stacked" src="{entry["image_url"]}" alt="{entry["title"]}" loading="lazy" onerror="this.style.display=\'none\'">'
            else:
                image_html = f'<img class="grid-thumb" src="{entry["image_url"]}" alt="{entry["title"]}" loading="lazy" onerror="this.style.display=\'none\'">'
        # Truncate to ~180 chars but don't split words
        summary = entry.get("summary", "")
        if len(summary) > 180:
            summary = summary[:180].rsplit(" ", 1)[0] + "…"
        items += f"""
        <article class="grid-item">
            <h3>{entry["title"]}</h3>
            {image_html}
            <p>{summary}</p>
            {source_html}
        </article>
        """
    return f'<div class="grid" style="--columns: {columns}">{items}</div>'


def css() -> str:
    """Grid layout CSS — newspaper-style floated thumbnails (desktop) or stacked (mobile)."""
    return """
    .grid {
        display: grid;
        grid-template-columns: repeat(var(--columns, 2), 1fr);
        gap: 0.75rem;
        margin-bottom: 0.75rem;
        padding-bottom: 0.75rem;
        border-bottom: 1px solid var(--color-border-light, #eee);
    }
    .grid-item {
        border-left: 2px solid var(--color-accent, #0066cc);
        padding-left: 0.65rem;
        overflow: hidden;
        break-inside: avoid;
        page-break-inside: avoid;
    }
    .grid-item h3 {
        font-size: 0.9rem;
        margin-bottom: 0.2rem;
        word-wrap: break-word;
        overflow-wrap: break-word;
    }
    .grid-thumb {
        float: left;
        width: var(--thumbnail-width, 120px);
        height: auto;
        margin: 0 0.6rem 0.3rem 0;
        border: 1px solid var(--color-border-light, #eee);
        object-fit: contain;
        background: #f5f5f5;
    }
    /* Mobile: stacked thumbnails — constrained height to prevent page cuts */
    .grid-thumb--stacked {
        float: none;
        display: block;
        width: 100%;
        max-height: 360px;
        margin: 0 0 0.5rem 0;
        object-fit: contain;
    }
    .grid-item p {
        font-size: 0.78rem;
        line-height: 1.35;
        color: var(--color-text-muted, #555);
        word-wrap: break-word;
        overflow-wrap: break-word;
        hyphens: auto;
    }
    .grid-item .source-link {
        display: block;
        margin-top: 0.2rem;
        font-size: 0.7rem;
    }
    """

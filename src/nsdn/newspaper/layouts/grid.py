"""Grid layout — multi-column article list."""

from __future__ import annotations


def render(entries: list[dict], columns: int = 2, css_vars: dict | None = None) -> str:
    """Render a grid of articles."""
    css_vars = css_vars or {}
    items = ""
    for entry in entries:
        link_html = f'<a href="{entry["link"]}" class="source-link">— [Source ↗]({entry["link"]})</a>' if entry.get("link") else ""
        image_html = ''
        if entry.get("image_url"):
            image_html = f'<img src="{entry["image_url"]}" alt="{entry["title"]}" loading="lazy">'
        items += f"""
        <article class="grid-item">
            <h3>{entry["title"]}</h3>
            {image_html}
            <p>{entry["summary"][:150]}</p>
            {link_html}
        </article>
        """
    return f'<div class="grid" style="--columns: {columns}">{items}</div>'


def css() -> str:
    """Grid layout CSS."""
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
    }
    .grid-item h3 {
        font-size: 0.95rem;
        margin-bottom: 0.25rem;
    }
    .grid-item img {
        max-width: 100%;
        height: auto;
        display: block;
        margin: 0.3rem 0;
        border: 1px solid var(--color-border-light, #eee);
    }
    .grid-item p {
        font-size: 0.8rem;
        line-height: 1.4;
        color: var(--color-text-muted, #555);
    }
    """

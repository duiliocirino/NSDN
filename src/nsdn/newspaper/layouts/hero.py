"""Hero layout — dominant lead story."""

from __future__ import annotations


def render(entry: dict, css_vars: dict | None = None) -> str:
    """Render a hero article layout — side-by-side with image on right."""
    css_vars = css_vars or {}
    image_html = ''
    if entry.get("image_url"):
        image_html = f'<div class="hero-image"><img src="{entry["image_url"]}" alt="{entry["title"]}" loading="lazy" onerror="this.style.display=\'none\'"></div>'
    source_html = f'<a href="{entry["link"]}" class="source-link" target="_blank" rel="noopener">Source ↗</a>' if entry.get("link") else ""
    return f"""
    <article class="hero">
        <div class="hero-content">
            <h1>{entry["title"]}</h1>
            <p class="hero-summary">{entry["summary"]}</p>
            {source_html}
        </div>
        {image_html}
    </article>
    """


def css() -> str:
    """Hero layout CSS — side-by-side with image on right."""
    return """
    .hero {
        border-bottom: 2px solid var(--color-border, #333);
        padding-bottom: 1rem;
        margin-bottom: 1.5rem;
        display: flex;
        gap: 1rem;
        align-items: flex-start;
    }
    .hero-content {
        flex: 1;
        min-width: 0;
    }
    .hero h1 {
        font-size: var(--hero-size, 1.4rem);
        line-height: 1.15;
        margin-bottom: 0.5rem;
        word-wrap: break-word;
        overflow-wrap: break-word;
    }
    .hero-summary {
        font-size: var(--hero-summary-size, 0.85rem);
        line-height: 1.5;
        color: var(--color-text, #333);
        margin-bottom: 0.5rem;
    }
    .hero-image {
        flex-shrink: 0;
        width: 280px;
    }
    .hero-image img {
        max-width: 100%;
        max-height: 240px;
        height: auto;
        display: block;
        border: 1px solid var(--color-border-light, #eee);
        object-fit: cover;
    }
    """

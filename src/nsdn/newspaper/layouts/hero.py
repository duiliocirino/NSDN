"""Hero layout — dominant lead story."""

from __future__ import annotations


def render(entry: dict, css_vars: dict | None = None) -> str:
    """Render a hero article layout."""
    css_vars = css_vars or {}
    image_html = ''
    if entry.get("image_url"):
        image_html = f'<img src="{entry["image_url"]}" alt="{entry["title"]}" loading="lazy">'
    return f"""
    <article class="hero">
        <h1>{entry["title"]}</h1>
        <p class="hero-summary">{entry["summary"]}</p>
        {image_html}
        {f'<a href="{entry["link"]}" class="source-link">— [Source ↗]({entry["link"]})</a>' if entry.get("link") else ""}
    </article>
    """


def css() -> str:
    """Hero layout CSS."""
    return """
    .hero {
        border-bottom: 2px solid var(--color-border, #333);
        padding-bottom: 1rem;
        margin-bottom: 1.5rem;
    }
    .hero h1 {
        font-size: var(--hero-size, 1.4rem);
        line-height: 1.15;
        margin-bottom: 0.5rem;
    }
    .hero-summary {
        font-size: var(--hero-summary-size, 0.85rem);
        line-height: 1.5;
        color: var(--color-text, #333);
        margin-bottom: 0.5rem;
    }
    .hero img {
        max-width: 100%;
        height: auto;
        display: block;
        margin: 0.5rem 0;
        border: 1px solid var(--color-border-light, #eee);
    }
    """

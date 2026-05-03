"""Sidebar layout — related entries and context."""

from __future__ import annotations


def render(entries: list[dict], css_vars: dict | None = None) -> str:
    """Render a sidebar with related entries."""
    css_vars = css_vars or {}
    items = ""
    for entry in entries:
        source_html = f'<a href="{entry["link"]}" class="source-link" target="_blank" rel="noopener">Source ↗</a>' if entry.get("link") else ""
        items += f"""
        <div class="sidebar-item">
            <h4>{entry["title"]}</h4>
            {source_html}
        </div>
        """
    return f'<aside class="sidebar">{items}</aside>'


def css() -> str:
    """Sidebar layout CSS — matches grid-item styling for visual consistency."""
    return """
    .sidebar {
        margin-bottom: 0.5rem;
    }
    .sidebar-item {
        border-left: 2px solid var(--color-accent, #0066cc);
        padding-left: 0.65rem;
        margin-bottom: 0.65rem;
        padding-bottom: 0.65rem;
    }
    .sidebar-item:last-child {
        margin-bottom: 0;
        padding-bottom: 0;
    }
    .sidebar-item h4 {
        font-size: 0.95rem;
        margin-bottom: 0.25rem;
    }
    """

"""Sidebar layout — related entries and context."""

from __future__ import annotations


def render(entries: list[dict], mode: str = "desktop", css_vars: dict | None = None) -> str:
    """Render a sidebar with related entries.
    
    Desktop: left border accent
    Mobile: top border accent
    """
    css_vars = css_vars or {}
    items = ""
    for entry in entries:
        source_html = f'<a href="{entry["link"]}" class="source-link" target="_blank" rel="noopener">Source ↗</a>' if entry.get("link") else ""
        cls = "sidebar-item sidebar-item--top" if mode == "mobile" else "sidebar-item"
        items += f"""
        <div class="{cls}">
            <h4>{entry["title"]}</h4>
            {source_html}
        </div>
        """
    return f'<aside class="sidebar">{items}</aside>'


def css() -> str:
    """Sidebar layout CSS — left border (desktop) or top border (mobile)."""
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
    /* Mobile: top border instead of left */
    .sidebar-item--top {
        border-left: none;
        border-top: 2px solid var(--color-accent, #0066cc);
        padding-left: 0;
        padding-top: 0.65rem;
    }
    .sidebar-item h4 {
        font-size: 0.95rem;
        margin-bottom: 0.25rem;
    }
    """

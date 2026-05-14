# Mobile/Desktop Mode — Design Plan

## Goal
Every edition has both mobile and desktop versions. User chooses which to view.

## Approach Options

### Option A: Responsive CSS (single file)
- Use CSS media queries to adapt layout
- One HTML file, different rendering per viewport
- **Problem:** WeasyPrint ignores media queries → can't generate mobile PDFs
- **Verdict:** ❌ Not viable for PDF output

### Option B: Dual Generation (two LLM passes)
- Generate layout twice: once for mobile, once for desktop
- Different component structures per viewport
- **Problem:** 2x LLM cost, 2x generation time
- **Verdict:** ❌ Overkill for CSS-only differences

### Option C: CSS Variant (single layout, two renders) ← RECOMMENDED
- Generate layout ONCE (hero/grid/sidebar structure is viewport-agnostic)
- Render twice with different CSS:
  - Desktop: 2-column grid, side-by-side hero, smaller fonts
  - Mobile: 1-column grid, stacked hero, larger fonts
- **Benefit:** 1x LLM cost, fast, full control over each version

## Layout Differences

| Element | Desktop | Mobile |
|---------|---------|--------|
| Container width | 794px (A4) | 375px (phone) |
| Font size | 0.85rem base | 1rem base |
| Grid columns | 2 | 1 |
| Hero layout | side-by-side (text + image) | stacked (image on top) |
| Hero image width | 280px | 100% |
| Grid thumbnails | float left, 120px | stacked, 100% width |
| Sidebar | left border accent | top border accent |
| Spacing | compact | more padding |

## Implementation Plan

### 1. CSS Generation (`generator.py`)
```python
def _build_base_css(fonts, colors, mode="desktop") -> str:
    # Mode-specific CSS variables
    if mode == "mobile":
        vars = {
            "--container-width": "100%",
            "--font-size-base": "1rem",
            "--grid-columns": "1",
            "--hero-size": "1.3rem",
            "--spacing": "1.5rem",
        }
    else:
        vars = {
            "--container-width": "794px",
            "--font-size-base": "0.85rem",
            "--grid-columns": "2",
            "--hero-size": "1.4rem",
            "--spacing": "1rem",
        }
```

### 2. Layout Rendering (`layouts/*.py`)
```python
# hero.py
def render(entry, mode="desktop") -> str:
    if mode == "mobile":
        # Stacked: image on top, text below
        return f'''
        <article class="hero hero--stacked">
            {image_html}
            <div class="hero-content">
                <h2>{title}</h2>
                <p>{summary}</p>
            </div>
        </article>'''
    else:
        # Side-by-side (current)
        ...
```

### 3. Generation Pipeline (`component.py`)
```python
def _design_topic(self, entries, topic) -> tuple[DesignedPage, DesignedPage]:
    # Generate layout ONCE
    html_spec, css_base = self.generator.generate(entries, topic)
    
    # Render desktop
    desktop_html = self._render_html(html_spec, mode="desktop")
    desktop_css = self._build_css(css_base, mode="desktop")
    
    # Render mobile
    mobile_html = self._render_html(html_spec, mode="mobile")
    mobile_css = self._build_css(css_base, mode="mobile")
    
    return (
        DesignedPage(desktop_html, desktop_css, score, topic),
        DesignedPage(mobile_html, mobile_css, score, topic)
    )
```

### 4. Output Structure
```
output/{user_id}/journal/{edition_slug}/
  cover.html          ← desktop
  cover-mobile.html
  edition.pdf         ← desktop
  edition-mobile.pdf
  topics/
    {topic}.html
    {topic}-mobile.html
    {topic}.pdf
    {topic}-mobile.pdf
```

### 5. Config (`config/nsdn.yaml`)
```yaml
newspaper:
  modes:
    desktop:
      viewport: {width: 794, height: 1123}
      grid_columns: 2
      base_font_size: 0.85rem
    mobile:
      viewport: {width: 375, height: 812}
      grid_columns: 1
      base_font_size: 1rem
```

## Files to Modify

| File | Change |
|------|--------|
| `config.py` | Add `ViewportMode` model to `NewspaperConfig` |
| `config/nsdn.yaml` | Add `modes` section |
| `generator.py` | `_build_base_css(mode)`, accept mode parameter |
| `layouts/hero.py` | `render(mode)`, stacked vs side-by-side |
| `layouts/grid.py` | `render(mode)`, 1 vs 2 columns, float vs stack |
| `layouts/sidebar.py` | `render(mode)`, top vs left border |
| `component.py` | `_design_topic()` returns 2 pages, `_assemble()` writes both |
| `renderer.py` | Accept mode parameter, use correct viewport |
| `prompts.py` | No change (layout spec is mode-agnostic) |

## Migration Path

1. **Phase 1:** CSS variables only (both modes use same HTML, different CSS)
2. **Phase 2:** Mode-specific HTML (stacked hero for mobile)
3. **Phase 3:** Config-driven (user can disable mobile generation)

## Evaluation Strategy

Both modes evaluated separately by default. Fast-path option for desktop-only.

```yaml
newspaper:
  evaluation:
    eval_modes: "full"  # "full" | "fast"
    # full: score desktop + mobile separately
    # fast: score desktop only, inherit to mobile
```

## Backward Compatibility

- Default: generate both modes
- Config flag: `newspaper.generate_mobile: true/false`
- Existing editions: desktop only (mobile added for new editions)

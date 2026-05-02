# Newspaper Agent — Design Document

## Overview

Design is a **synthesize mode** — an alternative to `"llm"` and `"raw"` journal output. Instead of writing a Markdown journal, it produces designed newspaper-style pages: per-topic pages with iterative VLM feedback, plus a cover page highlighting top stories.

```
Extract → Summarize → Filter → Synthesize
                                         │
                              output_mode (config.synthesize.mode):
                                - "llm"    → journal .md + .html (default)
                                - "raw"    → raw .md + .html
                                - "design" → designed topic pages + cover + edition
```

All modes share the same entry pool (`kept=1, processed_in_edition IS NULL`) and mark entries identically.

Output: HTML and PDF in parallel from the same source.

## Architecture

```
Synthesize (mode="design")
  │
  ├── ClusterStep → {topic: [entries]}
  │
  ├── TopicDesigner (per topic, iterative)
  │     │
  │     ├── LayoutGenerator → html + css
  │     ├── Renderer → html → screenshot (Playwright), pdf (WeasyPrint)
  │     ├── Evaluator → VLM screenshot review + text self-review
  │     └── (repeat until score >= threshold or max_iterations)
  │
  ├── CoverDesigner → reads cluster → HighlightSelector → cover.html
  │     └── HighlightSelector ABC (pluggable strategies)
  │           - TopScorePerTopic (default)
  │
  └── Assembler → edition.html + edition.pdf
```

## Module Structure

```
src/nsdn/newspaper/
├── __init__.py           # REGISTRY + register_newspaper() + get_newspaper()
├── base.py               # NewspaperStrategy ABC
├── component.py          # Component-based strategy (v1 implementation)
├── generator.py          # LayoutGenerator — composes HTML/CSS from components
├── renderer.py           # Renderer — HTML → screenshot (async, asyncio.run wrapper), pdf
├── evaluator.py          # Evaluator — VLM + text self-review (same design model)
├── cover.py              # CoverDesigner — front page from cluster highlights
├── selectors.py          # HighlightSelector ABC + TopScorePerTopic
├── prompts.py            # DESIGN_SYSTEM_PROMPT, EVALUATE_SYSTEM_PROMPT, etc.
└── layouts/              # Layout element definitions
    ├── __init__.py
    ├── hero.py           # Hero article layout
    ├── grid.py           # Multi-column grid layout
    ├── sidebar.py        # Sidebar layout
    ├── pullquote.py      # Pull quote layout (v2)
    └── statbox.py        # Data/stat layout (v2)
```

## Core Iterative Loop

```python
def design_topic(self, entries: list[FeedEntry], topic: str) -> DesignedPage:
    feedback = ""
    for _ in range(self.max_iterations):
        # Generate
        html, css = self.generator.generate(entries, topic, feedback)

        # Render
        screenshot = self.renderer.to_image(html, css)
        html_text = self.renderer.to_string(html, css)

        # Evaluate
        score, critique = self.evaluator.evaluate(screenshot, html_text, topic)

        if score >= self.quality_threshold:
            return DesignedPage(html, css, score)

        feedback = critique  # Feed back for next iteration
```

### Convergence Criteria

- **Score threshold**: configurable (default 7/10)
- **Max iterations**: configurable (default 4)
- If threshold not met after max iterations, accept the best score

## Subsystems

### 1. LayoutGenerator

Takes entries + topic + optional feedback, produces HTML/CSS.

**Component-based approach (v1):**

Predefined layout components, each describing its HTML structure and CSS:

| Component | Use Case | Visual |
|---|---|---|
| `Hero` | Lead story, large type, image | Full-width, prominent |
| `Grid` | 2-3 column article list with thumbnails | Responsive columns |
| `Sidebar` | Related entries, links | Narrow column, accent border |

**Images:** Hero and grid components automatically include the first image from `FeedEntry.images`. Sidebar stays text-only. Images use `loading="lazy"` and `max-width: 100%`.

**Fonts:** Four presets (classic, editorial, modern, newspaper). Configurable via `font_preset` and `fonts` override dict. Google Fonts `@import` auto-included when specified.

The generator produces a structured layout spec. The evaluator evaluates the same structure.

**Generator output schema:**
```json
{
  "layout": {
    "components": [
      {"type": "hero", "entry_guid": "...", "role": "lead_story"},
      {"type": "grid", "entry_guids": ["...", "..."], "role": "supporting"},
      {"type": "sidebar", "entry_guids": ["..."], "role": "related"}
    ],
    "style": {
      "hierarchy": "hero-dominant",
      "columns": 2,
      "spacing": "comfortable"
    }
  }
}
```

**Generator prompt:**
```
System: You are a newspaper layout designer.
Compose pages from layout elements: Hero, Grid, Sidebar, PullQuote, StatBox.

Design principles:
  - Hierarchy: one dominant lead story (Hero), supporting entries (Grid), context (Sidebar)
  - Balance: distribute whitespace evenly, avoid cramped sections
  - Readability: limit line length, ensure contrast between sections
  - Cohesion: consistent typography, aligned margins, professional appearance

Output JSON with "layout" containing "components" array and "style" object.
Each component must specify type, entry references, and role.
```

Generator renders the layout spec to HTML using Jinja2 templates.

### 2. Renderer

Two rendering paths from the same HTML/CSS:

#### HTML → Screenshot (for VLM)

- **Tool**: Playwright (headless Chromium)
- **Why**: Accurate rendering of modern CSS, reliable screenshot
- **Output**: PNG at A4 viewport (794×1123px at 96dpi) — matches final PDF page size
- **DPI**: 300 (print-quality screenshots for accurate VLM evaluation)

```python
async def to_image(self, html: str, css: str) -> bytes:
    page = await self.browser.new_page()
    await page.goto(f"data:text/html,{html_with_css}")
    await page.wait_for_load_state("networkidle")
    return await page.screenshot(type="png", scale="device")
```

#### HTML → PDF

- **Tool**: WeasyPrint
- **Why**: CSS Paged Media, local, no API, BSD license
- **Config**: A4 or Letter, margins via `@page` (not `* { padding }`)
- **Note**: Combined edition PDF merges all per-topic CSS, not just cover CSS

```python
def to_pdf(self, html: str, css: str) -> bytes:
    doc = HTML(string=html_with_css)
    return doc.write_pdf(presentation={"@page": {"size": "A4", "margin": "20mm"}})
```

#### HTML → Static HTML (standalone)

- Inline CSS, embed images, self-contained file

### 3. Evaluator

Hybrid evaluation — text self-review + VLM visual review. Both evaluate the same four criteria the generator was instructed to follow.

#### Text Self-Review

Evaluates the generator's JSON layout spec against the design principles:

```
System: You are a layout reviewer. Evaluate this layout specification.

Criteria (evaluate each, then give overall score):
  1. Hierarchy: Is there one dominant lead story? Are supporting entries clearly secondary?
  2. Balance: Are whitespace and visual weight distributed evenly?
  3. Readability: Are sections distinct? Is the component selection appropriate for the entry count?
  4. Cohesion: Do the style choices (columns, spacing, hierarchy) form a consistent design?

Score 1-10 with specific actionable critique.
```

Input: the generator's JSON layout spec (components array + style object).

#### VLM Screenshot Review

Evaluates the rendered HTML against the same four criteria:

```
System: You are a visual design critic. Evaluate this newspaper page screenshot.

Criteria (evaluate each, then give overall score):
  1. Hierarchy: Is the lead story visually dominant? Can you identify it at a glance?
  2. Balance: Is whitespace distributed well? Does any section feel cramped or empty?
  3. Readability: Is type size appropriate? Are sections clearly separated?
  4. Cohesion: Does it look like a professional publication with consistent styling?

Score 1-10 with specific actionable critique referencing these four criteria.
```

Input: screenshot PNG + topic name.

#### Combined Score

```
final_score = (text_score * 0.3) + (vlm_score * 0.7)
```

VLM weighted higher — it sees the actual rendered output.

### 4. CoverDesigner

Front page that highlights top stories from the cluster. Uses pluggable `HighlightSelector` strategies.

**Input:** Cluster output `{topic: [entries]}` — same data used for topic pages.

**HighlightSelector ABC (registry pattern):**

```python
class HighlightSelector(ABC):
    @abstractmethod
    def select(self, entries_by_topic: dict[str, list[FeedEntry]]) -> list[FeedEntry]: ...

# Default: top-scored entry per topic
class TopScorePerTopic(HighlightSelector):
    def select(self, entries_by_topic):
        return [max(entries, key=lambda e: e.score) for entries in entries_by_topic.values()]
```

Future strategies: editorial variety (LLM picks), most shared, oldest/newest, etc.

**Cover generation:** Single-pass (no iteration). Masthead + date/slot, featured entries with brief excerpts, refs to topic pages.

```python
def design_cover(self, entries_by_topic: dict[str, list[FeedEntry]]) -> tuple[str, str]:
    highlights = self.selector.select(entries_by_topic)
    html, css = self.generator.generate_cover(highlights, entries_by_topic)
    return html, css
```

## Configuration

```yaml
newspaper:
  enabled: true
  strategy: "component"        # component | template | scratch
  max_iterations: 4
  quality_threshold: 7
  viewport:
    width: 794                 # A4 at 96dpi
    height: 1123
  screenshot:
    dpi: 300
  pdf:
    format: "A4"
    margin: "20mm"
  font_preset: "editorial"     # classic | editorial | modern | newspaper
  fonts:                       # Override individual font values
    serif: "Georgia, 'Times New Roman', serif"
    sans: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    google_fonts: ""           # Optional: Google Fonts @import URL
  evaluation:
    text_weight: 0.3
    vlm_weight: 0.7
  cover:
    enabled: true
    style: "minimal"           # minimal | bold | classic
  layouts:
    enabled:
      - hero
      - grid
      - sidebar
```

## LLM Requirements

Two model configs: `llm.models.design` for generation + text review, `llm.models.evaluate` for VLM evaluation.

Each design iteration uses three LLM calls:

| Task | Model | Config Key |
|---|---|---|
| Layout generation | Text LLM | `llm.models.design` |
| Text self-review | Text LLM | `llm.models.design` |
| VLM evaluation | Multimodal VLM | `llm.models.evaluate` |

Total per topic: `max_iterations × 3` calls (4 × 3 = 12 with defaults).

Per-stage model config is defined in `docs/DESIGN.md` — the agent looks up models by name via `create_provider(config.llm, model_name="design")` or `create_provider(config.llm, model_name="evaluate")`.

## Usage

Design is selected via `config.synthesize.mode`:

```yaml
synthesize:
  mode: "design"    # llm | raw | design
```

```
nsdn run          → full pipeline with mode from config
nsdn synthesize   → standalone synthesize with mode from config
```

To switch modes, change `config.synthesize.mode` or pass `--mode` (future CLI flag).

## Entry Tracking

Design uses the same tracking as synthesize — `processed_in_edition`. Entries designed in one run won't be picked up again until the next extraction cycle brings in new content.

### Registry Pattern

Two registries — newspaper strategy and highlight selector:

```python
# newspaper/__init__.py
REGISTRY = {}
def register_newspaper(name: str, cls: type) -> None: ...
def get_newspaper(name: str) -> type: ...

# newspaper/selectors.py
SELECTOR_REGISTRY = {}
def register_selector(name: str, cls: type) -> None: ...
def get_selector(name: str) -> type: ...
```

Dispatch in synthesize when `mode == "design"`:

```python
if config.synthesize.mode == "design":
    strategy_cls = get_newspaper(config.newspaper.strategy)
    agent = strategy_cls(config)
    return agent.run_design(config, db, llm)
```

## First Implementation Scope

**V1 — Component-based with VLM feedback, integrated as synthesize mode:**

1. `component.py` strategy with Hero + Grid + Sidebar components
2. Playwright renderer (screenshot via `asyncio.run()` wrapper)
3. WeasyPrint PDF renderer
4. Evaluator (VLM + text self-review, single `design` model)
5. Cover designer (single-pass, reads cluster)
6. `selectors.py` with `TopScorePerTopic` default
7. Assembler (combine into edition)
8. Dispatch in `synthesize.py` for `mode == "design"`
9. Config schema (`NewspaperConfig`)

**Implemented in V1:**
- Hero + Grid + Sidebar components
- Automatic image rendering (first image from `FeedEntry.images`)
- Font presets (classic, editorial, modern, newspaper) with Google Fonts support
- A4-matched screenshot viewport (794×1123px)
- Combined PDF with merged per-topic CSS
- Edition directory structure (`{date}-{slot}/` with `topics/` subdirectory)
- Debug emitter (structured trace + artifact storage)

**Out of scope for V1:**
- Template-based strategy
- Scratch (free-form) strategy
- PullQuote and StatBox components
- Additional highlight selectors (editorial variety, most shared)
- LLM multi-draft selection (let LLM choose which entries get images)

## Dependencies

| Dependency | Purpose | Install |
|---|---|---|
| `playwright` | Headless browser for screenshots | `poetry add playwright` + `playwright install chromium` |
| `weasyprint` | HTML → PDF | `poetry add weasyprint` |
| `jinja2` | Component templates | Already installed |

## Risk Assessment

| Risk | Impact | Mitigation |
|---|---|---|
| Playwright install complexity | Setup friction | Clear install instructions, fallback to text-only eval |
| VLM token cost (screenshots) | Slow iteration | Configurable DPI, max image size |
| LLM refuses to iterate | Stuck in bad design | Max iterations hard limit, always accept last |
| WeasyPrint CSS limitations | Rendering mismatch | Test against Playwright output |

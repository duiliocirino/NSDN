# NSDN — Design Document

## 1. Problem Statement

Content sources produce too much noise. The user wants a scheduled, AI-curated static digest that:
- Pulls from various sources (e.g., RSS feeds, APIs, Reddit) on a fixed schedule (3×/day)
- Summarizes long content through a local LLM, preserving tone and key facts
- Filters content through a local LLM based on user-defined interests
- Synthesizes a clean "journal edition" in Markdown → HTML (or designed newspaper pages)
- Serves it as a static page with zero JS, zero trackers, zero infinite scroll

## 2. Architecture Overview

```
Sources (EntrySource)  ──►  SQLite (State Mgr)  ──►  Weaviate (Semantic)
     │                          │
     │  extract                 │  exact dedup
     ▼                          ▼
  Reddit/RSS/...          GUID-based dedup
                                    │
                                    ▼
                              semantic dedup
                                    │
                                    ▼
                              LLM Summarize (long content → summary)
                                    │
                                    ▼
                              LLM Filter (score 0-10)
                                    │
                                    ▼
                              Synthesize (config.synthesize.mode):
                                - "llm"    → journal .md + .html
                                - "raw"    → raw .md + .html
                                - "design" → topic pages + cover + edition (html+pdf)

                              Deliver (planned):
                                - email    → SMTP / SendGrid / Mailgun
                                - telegram → Bot API (sendDocument)

**Pipeline stages:** Extract → Summarize → Filter → Synthesize → (Deliver)
```

Synthesize has three output modes:
- `"llm"` — LLM-written journal in Markdown + HTML
- `"raw"` — passthrough via designer, no LLM write step
- `"design"` — newspaper-style pages with iterative VLM feedback (see `docs/design/newspaper_agent.md`)

**Pluggable abstractions (registry pattern):**
- `EntrySource` — new data sources without touching pipeline code
- `PageDesigner` — new journal styles without touching render code
- `ClusterStrategy` — alternative clustering strategies
- `SummarizerStrategy` — alternative summarization strategies
- `LLMProvider` — alternative LLM backends
- `HighlightSelector` — strategies for selecting cover page highlights
- `NewspaperStrategy` — alternative newspaper agent implementations

## 3. Project Structure

```
nsdn/
├── config/
│   └── nsdn.yaml              # User configuration
├── docs/
│   ├── DESIGN.md              # This document
│   └── design/
│       ├── mobile-desktop.md  # Mobile/desktop dual-mode rendering design
│       ├── multi-tenant.md    # Multi-tenant architecture (planned)
│       └── newspaper_agent.md # Newspaper agent design
├── src/nsdn/
│   ├── __init__.py
│   ├── cli.py                 # Entry point (Click CLI)
│   ├── config.py              # Pydantic config models
│   ├── loader.py              # YAML → config loading
│   ├── extract.py             # Orchestrates sources → SQLite + Weaviate
│   ├── filter.py              # LLM scoring (batch or sequential)
│   ├── synthesize.py          # Cluster → write journal (md + html)
│   ├── render.py              # Standalone md → HTML (post-hoc utility)
│   ├── serve.py               # Lightweight HTTP server
│   ├── db.py                  # SQLite schema, queries, migrations
│   ├── debug.py               # DebugEmitter (structured trace + artifacts)
│   ├── llm.py                 # LLMProvider ABC + implementations
│   ├── prompts.py             # LLM prompt templates
│   ├── vector.py              # Weaviate client wrapper
│   ├── sources/               # Pluggable entry sources
│   │   ├── __init__.py        # SOURCE_REGISTRY + register/get
│   │   ├── base.py            # EntrySource ABC + FeedEntry model
│   │   └── reddit.py          # Reddit subreddit source (auto-registers)
│   ├── designers/             # Pluggable page designers
│   │   ├── __init__.py        # DESIGNER_REGISTRY + register/get
│   │   ├── base.py            # PageDesigner ABC
│   │   ├── pico.py            # Pico.css designer
│   │   └── water.py           # Water.css designer
│   ├── clusters/              # Pluggable clustering strategies
│   │   ├── __init__.py        # CLUSTER_REGISTRY + register/get/run
│   │   ├── base.py            # ClusterStrategy ABC
│   │   └── llm_cluster.py     # LLM-based clustering with per-topic limits
│   ├── summarizers/           # Pluggable summarization strategies
│   │   ├── __init__.py        # SUMMARIZER_REGISTRY + register/get/run
│   │   ├── base.py            # SummarizerStrategy ABC
│   │   └── llm_summarizer.py  # LLM-based summarization
│   ├── newspaper/             # Newspaper agent (design mode)
│   │   ├── __init__.py        # REGISTRY + register_newspaper() + run_newspaper()
│   │   ├── component.py       # ComponentStrategy (iterative VLM feedback)
│   │   ├── generator.py       # LayoutGenerator + font presets + mode-aware cover
│   │   ├── renderer.py        # Renderer (Playwright + WeasyPrint + pypdfium2 PDF→images)
│   │   ├── evaluator.py       # Evaluator (VLM + text self-review + multi-page eval)
│   │   ├── cover.py           # CoverDesigner
│   │   ├── prompts.py         # Design + evaluation prompts (single + multi-page)
│   │   ├── selectors.py       # HighlightSelector ABC + TopScorePerTopic
│   │   └── layouts/           # Layout components
│   │       ├── __init__.py
│   │       ├── hero.py        # Hero article (with image, mode-aware stacked layout)
│   │       ├── grid.py        # Grid (with thumbnails, mode-aware columns)
│   │       └── sidebar.py     # Sidebar (text-only, mode-aware border)
│   └── assets/                # Bundled static assets (future)
│       └── __init__.py
├── templates/
│   ├── pico.html              # Pico designer template
│   └── water.html             # Water designer template
├── output/journal/            # Generated editions
│   ├── assets/                # Cached images (when cache_images=true)
│   └── {date}-{slot}/         # Edition directory (design mode)
│       ├── cover.html
│       ├── cover-mobile.html
│       ├── edition.pdf        # Combined multi-page PDF (desktop A4)
│       ├── edition-mobile.pdf # Combined multi-page PDF (mobile 375x812)
│       └── topics/            # Per-topic pages
│           ├── {topic}.html
│           ├── {topic}.pdf
│           └── {topic}-mobile.pdf
├── output/debug/              # Debug artifacts (when debug=true)
│   └── {date}-{slot}/
│       └── {topic}/
│           ├── iter0.html
│           ├── iter0-mobile.html
│           ├── iter0_spec.json
│           ├── desktop-page0.png
│           ├── mobile-page0.png
│           └── mobile-page1.png
├── data/
│   └── feeds.db               # SQLite database
├── pyproject.toml
└── README.md
```

**Note:** RSS, HackerNews, and X/Twitter sources are planned but not yet implemented.
The `schedule` field in config defines run times; actual scheduling is handled externally (cron or systemd timer).

## 4. Source Abstraction

All data sources implement a common interface. The extract phase is source-agnostic — it iterates over configured sources, collects `FeedEntry` objects, and inserts them into SQLite.

**FeedEntry model** — every source produces entries in this format:

```python
class FeedEntry(BaseModel):
    source_type: str        # "rss" | "hackernews" | "reddit" | ...
    source_name: str        # human-readable source identifier
    guid: str               # unique ID for deduplication
    title: str
    summary: str | None     # source-provided summary (e.g., truncated content)
    content: str | None
    link: str | None
    published_at: datetime  # ISO 8601
    author: str | None
    tags: list[str]         # source-specific metadata (subreddit, flair, etc.)
    images: list[str]       # image URLs (first is "featured")
```

### Base class

```python
class EntrySource(ABC):
    source_type: str

    def __init__(self, name: str, config: dict[str, Any]):
        self.name = name
        self.config = config

    @abstractmethod
    def fetch(self) -> list[FeedEntry]: ...

    def validate(self) -> bool:
        return True
```

### Source registry

Dynamic registry with auto-registration via module import:

```python
# src/sources/__init__.py
SOURCE_REGISTRY: dict[str, type[EntrySource]] = {}

def register_source(source_type: str, source_class: type[EntrySource]) -> None:
    SOURCE_REGISTRY[source_type] = source_class

def get_source(source_type: str) -> type[EntrySource]:
    if source_type not in SOURCE_REGISTRY:
        raise ValueError(f"Unknown source type: {source_type}. Available: {list(SOURCE_REGISTRY.keys())}")
    return SOURCE_REGISTRY[source_type]

# Auto-register by importing implementations
import nsdn.sources.reddit  # noqa: F401  (registers "reddit")
```

Same pattern applies to designers, clusters, and summarizers.

### PageDesigner ABC

Each designer encapsulates template, CSS, and Markdown rendering rules:

```python
class PageDesigner(ABC):
    designer_type: str

    def __init__(self, config: dict[str, Any]):
        self.config = config

    @abstractmethod
    def get_template_path(self) -> str: ...

    @abstractmethod
    def get_css(self) -> str: ...

    def get_css_url(self) -> str:
        return ""

    def render_entry(self, entry: FeedEntry) -> str:
        # Formats as: ### Title, image, summary, — [Source ↗](link)
        ...

    def render_edition(self, entries_by_topic: dict[str, list[FeedEntry]],
                       edition_date: str, slot: str) -> str:
        # Assembles ## Topic sections with formatted entries
        ...

    def get_context(self, content: str, edition_date: str, slot: str) -> dict[str, Any]:
        # Returns Jinja2 template context
        ...
```

### Default implementations

**PicoDesigner** — Pico.css (linked CDN):
```python
class PicoDesigner(PageDesigner):
    designer_type = "pico"
    def get_template_path(self) -> str: return "templates/pico.html"
    def get_css_url(self) -> str:
        return "https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css"
```

**WaterDesigner** — Water.css (inline):
```python
class WaterDesigner(PageDesigner):
    designer_type = "water"
    def get_template_path(self) -> str: return "templates/water.html"
    def get_css(self) -> str: return self._load_css("assets/water.min.css")
```

## 5. Configuration

Single YAML file (`config/nsdn.yaml`):

```yaml
debug: false        # Enable structured debug trace + artifact storage

interests:
  - "AI/ML research and tools"
  - "Finance and economics"
  # ...

sources:
  - type: reddit
    name: "r/LocalLLaMA"
    config:
      subreddit: "LocalLLaMA"
      sort: "hot"
      limit: 25
      time_filter: "day"

summarize:
  enabled: true
  strategy: "llm"
  batch_size: 10
  max_content_chars: 8000
  max_summary_chars: 8000
  min_length: 1000          # only summarize content longer than this

filter:
  mode: "batch"            # "batch" | "sequential"
  batch_size: 10
  score_threshold: 8
  max_items_per_feed: 25

synthesize:
  mode: "design"           # "llm" | "raw" | "design"
  cluster_strategy: "llm"
  raw_content: "summary"   # "summary" | "truncated" | "full"
  raw_max_chars: 2000
  max_sections: 10
  style: "technical_minimal"

output:
  directory: "./output/journal"
  designer: "pico"
  inline_css: true
  cache_images: false

retention:
  keep_days: 30
  action: "archive"

llm:
  default:
    provider: "llama_server"
    model: "gemma4-e4b"
    base_url: "http://localhost:8181"
    temperature: 0.7
    max_tokens: 131072

  # Per-stage overrides (optional)
  models:
    filter:
      provider: "ollama"
      model: "phi4"
    summarize:
      provider: "llama_server"
      model: "qwen2.5-7b"
    design:          # Layout generation + text self-review
      provider: "llama_server"
      model: "gemma4-e4b"
    evaluate:        # VLM screenshot evaluation
      provider: "llama_server"
      model: "qwen2.5-vl-7b"

# Newspaper agent config (when synthesize.mode = "design")
newspaper:
  enabled: true
  strategy: "component"       # "component" | "template" | "scratch"
  max_iterations: 4
  quality_threshold: 8
  eval_modes: "full"          # "full" (both modes) | "fast" (desktop only)
  generate_mobile: true       # Generate separate mobile edition PDF
  viewport:
    width: 794          # A4 at 96dpi
    height: 1123
  screenshot:
    dpi: 300
  pdf:
    format: "A4"
    margin: "20mm"
  cover:
    style: "minimal"
  layouts:
    - "hero"
    - "grid"
    - "sidebar"
  modes:                        # Viewport modes for dual-mode rendering
    desktop:
      label: "desktop"
      viewport: { width: 794, height: 1123 }
      grid_columns: 2
      base_font_size: "0.85rem"
      hero_font_size: "1.4rem"
      hero_summary_size: "0.85rem"
      hero_image_width: "280px"
      thumbnail_width: "120px"
      spacing: "1rem"
    mobile:
      label: "mobile"
      viewport: { width: 375, height: 812 }
      grid_columns: 1
      base_font_size: "1rem"
      hero_font_size: "1.3rem"
      hero_summary_size: "0.95rem"
      hero_image_width: "100%"
      thumbnail_width: "100%"
      spacing: "1.5rem"
  font_preset: "editorial"      # classic | editorial | modern | newspaper
  fonts:                        # Override individual font values
    serif: "Georgia, 'Times New Roman', serif"
    sans: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    google_fonts: ""            # Optional: Google Fonts @import URL
  colors:                       # Customizable color palette
    text: "#333"
    text-muted: "#555"
    border: "#333"
    border-light: "#eee"
    accent: "#0066cc"
  evaluation:
    text_weight: 0.3
    vlm_weight: 0.7

weaviate:
  enabled: true
  url: "http://localhost:8080"
  embedding_model: "qwen3-embedding:8b"
  embedding_endpoint: "http://localhost:11434"
  dedup_threshold: 0.95
  collection_name: "NSDNEntries"

schedule:
  - "08:00"
  - "13:00"
  - "19:00"
```

### Config models (Pydantic)

```python
class ProviderConfig(BaseModel):
    provider: str = "llama_server"
    model: str = ""
    base_url: str = "http://localhost:8181"
    temperature: float = 0.7
    max_tokens: int = 131072

class LLMConfig(BaseModel):
    default: ProviderConfig
    models: dict[str, ProviderConfig] = {}

    def get(self, stage: str) -> ProviderConfig:
        # Returns stage override merged with default, or default
        ...

class ViewportMode(BaseModel):
    label: str = "desktop"
    viewport: dict[str, int] = {"width": 794, "height": 1123}
    grid_columns: int = 2
    base_font_size: str = "0.85rem"
    hero_font_size: str = "1.4rem"
    hero_summary_size: str = "0.85rem"
    hero_image_width: str = "280px"
    thumbnail_width: str = "120px"
    spacing: str = "1rem"

class NewspaperConfig(BaseModel):
    enabled: bool = True
    strategy: str = "component"
    max_iterations: int = 4
    quality_threshold: int = 8
    eval_modes: str = "full"       # "full" | "fast"
    generate_mobile: bool = True
    modes: dict[str, ViewportMode]  # "desktop" + "mobile" defaults
    layouts: list[str] = ["hero", "grid", "sidebar"]
    # ... plus viewport, screenshot, pdf, cover, font_preset, fonts, colors, evaluation
```

## 6. Weaviate Integration

NSDN uses Weaviate as the **Semantic Engine** for deduplication.

**Config fields** (actual `WeaviateConfig`):

| Field | Type | Default |
|---|---|---|
| `enabled` | bool | `true` |
| `url` | str | `"http://localhost:8080"` |
| `embedding_model` | str | `"qwen3-embedding:8b"` |
| `embedding_endpoint` | str | `"http://localhost:11434"` |
| `dedup_threshold` | float | `0.95` |
| `collection_name` | str | `"NSDNEntries"` |

**Embedding strategy:** `semantic_text` property = concatenation of `title` + `summary`. Weaviate's embedding module generates vectors on ingest.

## 7. Database Schema (SQLite)

```sql
CREATE TABLE sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    name TEXT NOT NULL,
    source_config TEXT,
    UNIQUE(source_type, name)
);

CREATE TABLE entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    guid TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    content TEXT,
    link TEXT,
    published_at TEXT,
    author TEXT,
    tags TEXT,
    images TEXT,
    score REAL,
    kept BOOLEAN DEFAULT 0,
    summarized BOOLEAN DEFAULT 0,
    processed_in_edition TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

CREATE TABLE editions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    slot TEXT NOT NULL,
    markdown_file TEXT,
    html_file TEXT,
    entry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, slot)
);

-- Indexes
CREATE INDEX idx_entries_kept ON entries(kept);
CREATE INDEX idx_entries_processed ON entries(processed_in_edition);
CREATE INDEX idx_entries_score ON entries(score);
```

**Migrations:** `_migrate()` in `Database` checks columns via `PRAGMA table_info()` and applies `ALTER TABLE` as needed.

**Deduplication:** Entries are deduplicated by `guid`. Re-running extract won't duplicate.

## 8. Pipeline Details

### 8.1 Extract (`nsdn extract`)

1. Read `sources` from config
2. For each source, instantiate via `get_source(type)` from registry
3. Call `source.fetch()` → `list[FeedEntry]`
4. **Exact Dedup:** Skip entries with existing GUID in SQLite
5. **Semantic Dedup:** Query Weaviate for similar vectors. If cosine similarity > `dedup_threshold`, discard
6. **Ingest:** Insert surviving entries into SQLite AND Weaviate

### 8.2 Summarize (`nsdn summarize`)

Generates LLM summaries for entries with long content:

1. Query: `SELECT guid, content FROM entries WHERE content IS NOT NULL AND LENGTH(content) > min_length AND summarized = 0`
2. Batch entries, send to LLM via `invoke_structured()`
3. Persist summaries to SQLite, mark `summarized = 1`

**Pydantic schema:**
```python
class SummaryResult(BaseModel):
    summaries: dict[str, str]  # guid → summary
```

**System prompt:** Summarize while preserving original tone, key facts, and nuance. Max `max_summary_chars` characters.

**Registry:** `SummarizerStrategy` ABC + `LLMSummarizerStrategy` (auto-registers as `"llm"`).

### 8.3 Filter (`nsdn filter`)

Scores unscored entries (`score IS NULL`) and marks `kept`:

Two modes: `batch` (structured output, faster) or `sequential` (one-by-one, robust).

**Pydantic schema for batch mode:**
```python
class ScoreResult(BaseModel):
    scores: dict[str, int]  # guid → score
```

**Filter system prompt (actual):**
```
You are a content curator for NSDN (No Social Detox News).
Score entries based ONLY on the reader's stated interests.

Scoring scale (0-10):
  0-2: Completely irrelevant to the reader
  3-5: Low value — tangentially related or too niche
  6-7: Moderately relevant (usually skip)
  8-9: Genuinely useful for the reader (keep)
  10: Exceptional match (must-read)

IMPORTANT: You are curating, not rating.
- Only ~10-20% of entries should score 8+
- A 6 means "meh, skip it"
- If in doubt, score lower
```

### 8.4 Cluster

Groups kept entries by topic using `ClusterStrategy` registry:

**Pydantic schema (actual):**
```python
class ClusterResult(BaseModel):
    topics: dict[str, list[str]]  # topic_name → [guids]
    limits: dict[str, int]        # topic_name → how many to feature
```

**Cluster system prompt (actual):**
```
You are a content organizer. Group these entries into topics and decide
how many to feature per topic. Use specific, descriptive topic names.
Respond ONLY with valid JSON:
{"topics": {"topic_name": [guid1, guid2, ...]}, "limits": {"topic_name": count}}
```

**Registry:** `ClusterStrategy` ABC + `LLMClusterStrategy` (auto-registers as `"llm"`).

### 8.5 Synthesize (`nsdn synthesize`)

Three-step: **Cluster → Write → (optional) Design**.

**Mode `llm`:** For each topic, LLM generates prose. Output: `{mode}-{date}-{slot}.md` + `.html`.
**Mode `raw`:** Passthrough via designer, no LLM write step.
**Mode `design`:** Newspaper agent — iterative VLM feedback per topic, cover page, edition assembly. Output: `output/journal/{date}-{slot}/` directory.

**Design mode output structure:**
```
output/journal/{date}-{slot}/
├── cover.html
├── edition.pdf           # Combined multi-page PDF
└── topics/
    ├── {topic}.html
    └── {topic}.pdf
```

**Design mode features:**
- Automatic image rendering (first image from `FeedEntry.images` in hero/grid)
- Font presets (classic, editorial, modern, newspaper) with Google Fonts support
- A4-matched screenshot viewport (794×1123px) for consistent evaluation
- Combined PDF merges per-topic CSS (not just cover CSS)
- Debug emitter (`debug: true`) for structured trace + artifact storage
- **Mobile/Desktop dual-mode rendering** — single LLM layout spec, two CSS variants. Mobile uses 375×812 viewport, 1-column grid, stacked hero. Separate `edition-mobile.pdf` output.
- **Multi-page VLM evaluation** — PDF rendered to images via `pypdfium2`, all pages passed to VLM together for holistic cross-page assessment. Detects cut images, awkward page breaks, missing content.
- **Mobile cover generation** — mode-aware cover with 1-column grid and stacked hero.
- **Page-cut prevention** — `break-inside: avoid` on articles, `max-height: 360px` on mobile images to prevent page-boundary cuts.

See `docs/design/newspaper_agent.md` for full design agent specification.
See `docs/design/mobile-desktop.md` for dual-mode rendering details.

**Filenames:** `{mode}-{date}-{slot}.{ext}` (e.g., `llm-2025-01-15-morning.md`).

**Link format:** `— [Source ↗](url)` in all output modes.

**Entry tracking:** Sets `processed_in_edition = date`.

### 8.6 Render (`nsdn render`)

**Post-hoc utility** — not part of the main pipeline. Synthesize handles rendering inline.

`nsdn render -f file.md` — convert a single markdown file to HTML.
`nsdn render-all` — render all orphan `.md` files in the output directory.

Useful for re-rendering after CSS/template changes.

### 8.7 Serve (`nsdn serve`)

Lightweight HTTP server serving the output directory.

### 8.8 Full Run (`nsdn run`)

```
nsdn run          → extract → summarize → filter → synthesize (mode from config)
nsdn synthesize   → standalone synthesize (mode from config)
```

The synthesize mode is configured in `config.synthesize.mode`. Switch between `"llm"`, `"raw"`, and `"design"` by editing the config or passing `--mode` (future CLI flag).

### 8.9 CLI Commands

| Command | Description |
|---|---|
| `nsdn extract` | Fetch entries from all configured sources |
| `nsdn summarize` | Generate LLM summaries for long content |
| `nsdn filter` | Score and filter entries |
| `nsdn synthesize` | Cluster and write journal edition |
| `nsdn render -f FILE` | Render a single markdown file to HTML |
| `nsdn render-all` | Render all unrendered markdown files |
| `nsdn serve` | Serve output directory as static site |
| `nsdn run` | Full pipeline (mode from config) |
| `nsdn validate` | Validate all configured sources |

## 9. LLM Integration

The project ships with its own `LLMProvider` ABC and implementations (from MilleniumAI). Self-contained — no external LLM dependency.

**Registry pattern:**
```python
PROVIDER_REGISTRY: dict[str, type[LLMProvider]] = {}
def register_provider(name: str, cls: type) -> None: ...
def get_provider(name: str) -> type: ...
```

**Factory with per-stage model selection:**
```python
def create_provider(config: LLMConfig, model_name: str | None = None) -> LLMProvider:
    """Resolve stage config, create provider."""
    cfg = config.get(model_name) if model_name else config.default
    provider_type = cfg.provider
    # ... instantiate from PROVIDER_REGISTRY
```

Each pipeline stage passes its name to `create_provider(config.llm, model_name="stage")`.

## 10. Scheduling

**Cron:**
```cron
0 8,13,19 * * * cd /path/to/nsdn && poetry run nsdn run >> /var/log/nsdn.log 2>&1
```

**Systemd timer:**
```ini
# nsdn.service
[Service]
Type=oneshot
ExecStart=/usr/bin/poetry run nsdn run
WorkingDirectory=/path/to/nsdn

# nsdn.timer
[Timer]
OnCalendar=08:00,13:00,19:00
Persistent=true
```

## 11. Dependencies

```toml
dependencies = [
    "feedparser>=6.0",
    "pyyaml>=6.0",
    "jinja2>=3.1",
    "mistune>=3.0",
    "click>=8.1",
    "pydantic>=2.0",
    "weaviate-client>=4.0",
    "requests>=2.31",
    # LLM providers:
    "openai>=1.0",
    "ollama>=0.0",
    "llama-cpp-python>=0.1",
    # Newspaper agent:
    "playwright>=1.58.0,<2.0.0",
    "weasyprint>=68.1,<69.0",
    "pypdfium2>=5.8.0,<6.0.0",
]
```

**Dependency notes:**
- `playwright` — headless browser for screenshots (Chromium)
- `weasyprint` — HTML → PDF rendering (requires system fonts)
- `pypdfium2` — PDF → image conversion for multi-page VLM evaluation
- `openai` — OpenAI-compatible API (used by LlamaServerProvider)
- `ollama` — Ollama provider for local model inference
- `llama-cpp-python` — local GGUF model inference

## 12. Design Decisions & Tradeoffs

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Pluggable extension points | Strategy/Registry pattern | Consistent pattern across 5 extension points |
| Hybrid Storage | SQLite + Weaviate | SQLite for state/OLTP, Weaviate for semantic dedup |
| Per-stage LLM | `LLMConfig` with `default` + `models` dict | Different models for different tasks |
| YAML config | Pydantic models | Type-safe, human-readable |
| Click for CLI | Click | Clean subcommands, auto-generated help |
| Markdown intermediate | Yes (for synthesize) | Inspectable output |
| No web framework | Python http.server | Zero dependencies, static output |
| Schema migrations | Column-check + ALTER TABLE | Simple, no migration framework needed |

## 13. Future Considerations (Not in v1)

- **RSS/Atom source** — `rss.py` implementation (high priority — unblocks X via RSS bridge)
- **X/Twitter source** — via RSS bridge (rsshub.app) or X API v2 (paid tier)
- **HackerNews source** — `hackernews.py` implementation
- **Email delivery** — `src/nsdn/delivery/email.py` — SMTP or SendGrid/Mailgun API
- **Telegram delivery** — `src/nsdn/delivery/telegram.py` — Bot API (`sendMessage` + `sendDocument`)
- **Scheduled runs** — systemd timer or cron for fully automated pipeline
- **Feedback loop** — user rates editions, LLM learns preferences
- **Multi-user profiles** — separate configs per user
- **Archive browsing** — list past editions with search
- **Authentication** — if exposed beyond local network

## 14. Operational Features

### Retention & Archiving
Configurable retention. `cleanup_old_entries()` deletes entries older than `keep_days` that have been processed.

```yaml
retention:
  keep_days: 30
  action: "archive"  # "archive" | "delete"
```

### Score Distribution Stats
Planned: `nsdn stats` — score histograms per source.

### Dry-Run Mode
Planned: `nsdn run --dry-run` — preview without marking entries processed.

## 15. Implementation Status

| Component | Status |
|---|---|
| Core pipeline (extract → summarize → filter → synthesize) | ✅ Implemented |
| Per-stage LLM model selection | ✅ Implemented |
| Summarizers (LLM) | ✅ Implemented |
| Clusters (LLM with limits) | ✅ Implemented |
| Sources (Reddit) | ✅ Implemented |
| Designers (Pico, Water) | ✅ Implemented |
| Weaviate semantic dedup | ✅ Implemented |
| Newspaper agent (design as synthesize mode) | ✅ Implemented |
| Mobile/Desktop dual-mode rendering | ✅ Implemented |
| Multi-page VLM evaluation (pypdfium2) | ✅ Implemented |
| Mobile cover generation | ✅ Implemented |
| Page-cut prevention (break-inside + max-height) | ✅ Implemented |
| Highlight selectors (TopScorePerTopic) | ✅ Implemented |
| RSS/Atom source | ❌ Planned (high priority) |
| X/Twitter source (via RSS bridge) | ❌ Planned (high priority) |
| Email delivery | ❌ Planned (high priority) |
| Telegram delivery | ❌ Planned (high priority) |
| Scheduled runs (auto-publishing) | ❌ Planned (high priority) |
| HackerNews source | ❌ Planned |
| Dry-run mode | ❌ Planned |
| Score stats command | ❌ Planned |
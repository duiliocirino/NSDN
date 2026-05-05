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

**Pipeline stages:** Extract → Summarize → Filter → Synthesize

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

## 3. Project Structure

```
nsdn/
├── config/
│   └── nsdn.yaml              # User configuration
├── docs/
│   ├── DESIGN.md              # This document
│   └── design/
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
│   │   ├── __init__.py        # REGISTRY + register_newspaper()
│   │   ├── component.py       # ComponentStrategy (iterative VLM feedback)
│   │   ├── generator.py       # LayoutGenerator + font presets
│   │   ├── renderer.py        # Renderer (Playwright + WeasyPrint)
│   │   ├── evaluator.py       # Evaluator (VLM + text self-review)
│   │   ├── cover.py           # CoverDesigner
│   │   ├── prompts.py         # Design + evaluation prompts
│   │   ├── debug.py           # DebugEmitter (structured trace + artifacts)
│   │   └── layouts/           # Layout components
│   │       ├── hero.py        # Hero article (with image)
│   │       ├── grid.py        # Grid (with thumbnails)
│   │       └── sidebar.py     # Sidebar (text-only)
│   └── assets/                # Bundled static assets (future)
│       └── __init__.py
├── templates/
│   ├── pico.html              # Pico designer template
│   └── water.html             # Water designer template
├── output/journal/            # Generated editions
│   ├── assets/                # Cached images (when cache_images=true)
│   └── {date}-{slot}/         # Edition directory (design mode)
│       ├── cover.html
│       ├── edition.pdf        # Combined multi-page PDF
│       └── topics/            # Per-topic pages
│           ├── {topic}.html
│           └── {topic}.pdf
├── data/
│   └── feeds.db               # SQLite database
├── pyproject.toml
└── README.md
```

**Note:** RSS and HackerNews sources are planned but not yet implemented.

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
  max_summary_chars: 500
  min_length: 500          # only summarize content longer than this

filter:
  mode: "batch"            # "batch" | "sequential"
  batch_size: 15
  score_threshold: 7
  max_items_per_feed: 20

synthesize:
  mode: "llm"              # "llm" | "raw" | "design"
  cluster_strategy: "llm"
  raw_content: "summary"   # "summary" | "truncated" | "full"
  raw_max_chars: 2000
  max_sections: 5
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
    max_tokens: 4096

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
  strategy: "component"
  max_iterations: 4
  quality_threshold: 7
  viewport:
    width: 794          # A4 at 96dpi
    height: 1123
  screenshot:
    dpi: 300
  pdf:
    format: "A4"
    margin: "20mm"
  font_preset: "editorial"  # classic | editorial | modern | newspaper
  fonts:                      # Override individual font values
    serif: "Georgia, 'Times New Roman', serif"
    sans: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    google_fonts: ""          # Optional: Google Fonts @import URL
  colors:                     # Customizable color palette
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
    temperature: float = 0.0
    max_tokens: int = 4096

class LLMConfig(BaseModel):
    default: ProviderConfig
    models: dict[str, ProviderConfig] = {}

    def get(self, stage: str) -> ProviderConfig:
        # Returns stage override merged with default, or default
        ...
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

See `docs/design/newspaper_agent.md` for full design agent specification.

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
    "requests",
    # LLM providers (optional):
    # "llama-cpp-python",
    # "ollama",
    # "openai",
]
```

Planned dependencies for newspaper agent:
- `playwright` — headless browser for screenshots
- `weasyprint` — HTML → PDF

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

- **RSS/Atom source** — `rss.py` implementation
- **HackerNews source** — `hackernews.py` implementation
- **Email/Telegram delivery** — push editions
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
| RSS/Atom source | ❌ Planned |
| HackerNews source | ❌ Planned |
| Dry-run mode | ❌ Planned |
| Score stats command | ❌ Planned |
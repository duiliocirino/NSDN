# NSDN — Design Document

## 1. Problem Statement

Content sources produce too much noise. The user wants a scheduled, AI-curated static digest that:
- Pulls from various sources (e.g., RSS feeds, APIs, etc.) on a fixed schedule (3×/day)
- Filters content through a local LLM based on user-defined interests
- Synthesizes a clean, minimal "journal edition" in Markdown → HTML
- Serves it as a static page with zero JS, zero trackers, zero infinite scroll

## 2. Architecture Overview

```
┌─────────────────────────────┐    ┌──────────────┐     ┌──────────────┐
│         Sources             │    │   SQLite     │     │   Weaviate   │
│  ┌─────────────────────┐    │    │ (State Mgr)  │     │ (Semantic)   │
│  │ RSS / HN / Reddit / │  ──┼───►│              │ ───►│              │
│  │     ... any source  │    │    └──────────────┘     └──────┬───────┘
│  └─────────────────────┘    │                                │
│       (EntrySource)         │                                │
└─────────────────────────────┘                                │
                                                               │
                                                               ▼
                                                        ┌──────────────┐
                                                        │  LLM Filter  │
                                                        │   (Map)      │
                                                        └──────────────┘
                                                               │
                                                               ▼
                                                        ┌──────────────┐
                                                        │  LLM Editor  │
                                                        │   (Reduce)   │
                                                        └──────────────┘
                                                               │
                                                               ▼
                                                        ┌──────────────┐
                                                        │  Markdown    │
                                                        │  Journal     │
                                                        └──────────────┘
                                                               │
                                                               ▼
                                                        ┌──────────────┐
                                                        │  Static HTML │
                                                        │ (Jinja2 +    │
                                                        │  Designer)   │
                                                        └──────────────┘
                                                               │
                                                               ▼
                                                        ┌──────────────┐
                                                        │  HTTP Server │
                                                        │  (systemd)   │
                                                        └──────────────┘
```

**Pipeline stages:** Extract → Stage → Filter → Synthesize → Render → Serve

**Pluggable abstractions:**
- `EntrySource` — new data sources without touching pipeline code
- `PageDesigner` — new journal styles without touching render code

## 3. Project Structure

```
nsdn/
├── config/
│   └── nsdn.yaml              # User configuration (sources, topics, schedule)
├── src/
│   ├── __init__.py
│   ├── cli.py                 # Entry point: nsdn extract / filter / synthesize / serve / run
│   ├── extract.py             # Orchestrates all sources → SQLite
│   ├── filter.py              # LLM scoring (batch or sequential mode)
│   ├── synthesize.py          # LLM journal generation
│   ├── render.py              # Markdown → HTML via Jinja2
│   ├── serve.py               # Lightweight HTTP server
│   ├── db.py                  # SQLite schema and queries
│   ├── llm.py                 # LLMProvider ABC + implementations (from MilleniumAI)
│   ├── prompts.py             # LLM prompt templates
│   ├── sources/               # Pluggable entry sources
│   │   ├── __init__.py
│   │   ├── base.py            # EntrySource ABC + FeedEntry model
│   │   ├── rss.py             # RSS/Atom feed implementation
│   │   ├── hackernews.py      # Example: HN API source
│   │   └── reddit.py          # Example: Reddit subreddit source
│   └── designers/             # Pluggable page designers
│       ├── __init__.py
│       ├── base.py            # PageDesigner ABC
│       ├── pico.py            # Pico.css designer
│       └── water.py           # Water.css designer
├── output/
│   └── journal/               # Generated HTML editions (date-stamped)
│       └── assets/            # Cached images (when cache_images=true)
├── templates/
│   ├── pico.html              # Pico designer template
│   └── water.html             # Water designer template
├── assets/
│   └── water.min.css          # Bundled CSS for inline designers
├── data/
│   └── feeds.db               # SQLite database
├── pyproject.toml
└── README.md
```

## 4. Source Abstraction

All data sources implement a common interface. The extract phase is source-agnostic — it iterates over configured sources, collects `FeedEntry` objects, and inserts them into SQLite.

```
┌──────────────────────────────────────────────────────┐
│                  EntrySource (ABC)                    │
│                                                      │
│  + name: str                                         │
│  + source_type: str                                  │
│  + fetch() -> list[FeedEntry]   (abstract)           │
│  + validate() -> bool                                │
└──────────────┬───────────────────────────────────────┘
               │
    ┌──────────┼──────────┐
    │          │          │
    ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐
│  RSS   │ │   HN   │ │ Reddit │  ... any source
└────────┘ └────────┘ └────────┘
    │          │          │
    └──────────┼──────────┘
               │
               ▼
         ┌─────────────┐
         │  FeedEntry  │  (standardized)
         │  (Pydantic) │
         └──────┬──────┘
                │
                ▼
         ┌─────────────┐
         │   SQLite    │
         └─────────────┘
```

**FeedEntry model** — every source produces entries in this format:

```python
class FeedEntry(BaseModel):
    source_type: str        # "rss" | "hackernews" | "reddit" | ...
    source_name: str        # human-readable source identifier
    guid: str               # unique ID for deduplication
    title: str
    summary: str | None
    content: str | None
    link: str | None
    published_at: datetime  # ISO 8601
    author: str | None
    tags: list[str]         # source-specific metadata flattened into tags
    images: list[str]       # image URLs (first image is the "featured" image)
```

Images are extracted during `fetch()`:
- **RSS**: `<enclosure url="..." length="..." type="image/*">`, `<media:content url="..." medium="image">`, or first `<img>` tag in content
- **HN**: `default_images` from API
- **Reddit**: `thumbnail` or `preview.images[0].url` from API
- Sources with no images simply return `images=[]`

**Adding a new source** requires three steps:

1. Create `src/sources/my_source.py` inheriting from `EntrySource`
2. Implement `fetch()` — return `list[FeedEntry]`
3. Configure it in YAML with `type: my_source`

No changes to extract, filter, or synthesize logic. The pipeline doesn't know where entries came from.

### Base class

```python
from abc import ABC, abstractmethod
from typing import Any

class EntrySource(ABC):
    source_type: str

    def __init__(self, name: str, config: dict[str, Any]):
        self.name = name
        self.config = config

    @abstractmethod
    def fetch(self) -> list[FeedEntry]:
        """Fetch entries and return standardized FeedEntry objects."""
        ...

    def validate(self) -> bool:
        """Optional pre-flight check (e.g., connectivity, auth)."""
        return True
```

### Source registry

Sources are registered via a type map. New sources self-register:

```python
# src/sources/__init__.py
from .rss import RssSource
from .hackernews import HackerNewsSource

SOURCE_REGISTRY: dict[str, type[EntrySource]] = {
    "rss": RssSource,
    "hackernews": HackerNewsSource,
}

def get_source(source_type: str) -> type[EntrySource]:
    if source_type not in SOURCE_REGISTRY:
        raise ValueError(f"Unknown source type: {source_type}. Available: {list(SOURCE_REGISTRY.keys())}")
    return SOURCE_REGISTRY[source_type]
```

### PageDesigner ABC

Same pluggable pattern for journal styling. Each designer encapsulates template, CSS, and Markdown rendering rules.

```python
from abc import ABC, abstractmethod
from typing import Any

class PageDesigner(ABC):
    designer_type: str

    def __init__(self, config: dict[str, Any]):
        self.config = config

    @abstractmethod
    def get_template_path(self) -> str:
        """Return path to the Jinja2 template file."""
        ...

    @abstractmethod
    def get_css(self) -> str:
        """Return CSS string (for inline) or empty string (for linked)."""
        ...

    def get_css_url(self) -> str:
        """Return external CSS URL. Override if using linked CSS."""
        return ""

    def render_entry(self, entry: FeedEntry) -> str:
        """Render a single entry to Markdown. Override for custom formatting."""
        return f"### {entry.title}\\n{entry.summary}"

    def render_edition(self, entries_by_topic: dict[str, list[FeedEntry]], edition_date: str, slot: str) -> str:
        """Assemble full Markdown content from grouped entries."""
        sections = []
        for topic, entries in entries_by_topic.items():
            sections.append(f"## {topic}")
            for entry in entries:
                sections.append(self.render_entry(entry))
        return "\\n\\n".join(sections)

    def get_context(self, content: str, edition_date: str, slot: str) -> dict:
        """Build Jinja2 template context."""
        return {
            "title": f"NSDN — {edition_date} ({slot})",
            "date": edition_date,
            "slot": slot,
            "content": content,
            "css": self.get_css(),
            "css_url": self.get_css_url(),
            "inline_css": bool(self.get_css()),
        }
```

### Designer registry

```python
# src/designers/__init__.py
from .pico import PicoDesigner
from .water import WaterDesigner

DESIGNER_REGISTRY: dict[str, type[PageDesigner]] = {
    "pico": PicoDesigner,
    "water": WaterDesigner,
}

def get_designer(designer_type: str) -> type[PageDesigner]:
    if designer_type not in DESIGNER_REGISTRY:
        raise ValueError(f"Unknown designer: {designer_type}. Available: {list(DESIGNER_REGISTRY.keys())}")
    return DESIGNER_REGISTRY[designer_type]
```

### Adding a new designer

1. Create `src/designers/mydesigner.py` inheriting from `PageDesigner`
2. Provide a `templates/mydesigner.html` Jinja2 template
3. Override `get_css()` (inline) or `get_css_url()` (linked)
4. Register in `DESIGNER_REGISTRY`

No changes to the render pipeline. The pipeline calls `designer.render_edition()` and `designer.get_context()` — the rest is designer-specific.

### Default implementations

**PicoDesigner** — uses Pico.css (linked CDN or inline). Minimal overrides:

```python
class PicoDesigner(PageDesigner):
    designer_type = "pico"

    def get_template_path(self) -> str:
        return "templates/pico.html"

    def get_css_url(self) -> str:
        return "https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css"
```

**WaterDesigner** — uses Water.css (inline):

```python
class WaterDesigner(PageDesigner):
    designer_type = "water"

    def get_template_path(self) -> str:
        return "templates/water.html"

    def get_css(self) -> str:
        return self._load_css("assets/water.min.css")
```

## 5. Configuration

Users configure NSDN via a single YAML file (`config/nsdn.yaml`):

```yaml
# User interests — used to tune the LLM filter prompt
interests:
  - "AI/ML research and tools"
  - "Linux systems and embedded"
  - "Cybersecurity"

# Entry sources (pluggable, type-based)
sources:
  - type: rss
    name: "Hacker News"
    url: "https://hnrss.org/frontpage"
    max_items: 20

  - type: rss
    name: "LWN NetDev"
    url: "https://lwn.net/headlines/rss"
    max_items: 15

  - type: hackernews
    name: "HN Show HN"
    endpoint: "show"
    max_items: 10
    rate_limit: "1 req/5s"

# Weaviate configuration (reuses existing ai-stack)
weaviate:
  host: "localhost"
  port: 8080
  collection: "NSDNEntries"
  embedding_model: "qwen3-embedding:8b"
  semantic_dedup_threshold: 0.95

# LLM provider (self-contained, copied from MilleniumAI)
llm:
  provider: "llama_server"       # llama_server | llama_cpp | ollama
  model_path: "/path/to/model.gguf"  # for llama_cpp
  server_url: "http://localhost:8181" # for llama_server
  n_ctx: 16384
  n_gpu_layers: 999
  n_threads: 8

# Filter settings
filter:
  mode: "batch"                  # batch | sequential
  batch_size: 15                 # items per LLM call (batch mode)
  score_threshold: 7             # keep items with score >= this
  max_items_per_feed: 20         # cap entries fetched per feed per run

# Synthesis settings
synthesize:
  mode: "llm"                    # "llm" (synthesized) | "raw" (passthrough)
  raw_content: "summary"         # "summary" | "truncated" | "full" (used when mode=raw)
  raw_max_chars: 2000            # truncation limit for raw:truncated
  max_sections: 5                # max topic sections in the journal
  style: "technical_minimal"     # template for editor prompt

# Schedule (cron times, 24h format)
schedule:
  - "08:00"
  - "13:00"
  - "19:00"

# Output
output:
  directory: "./output/journal"
  designer: "pico"              # designer type (pico | water | custom)
  inline_css: true              # embed CSS in HTML (zero network requests)
  cache_images: false           # download images to assets/ (false = remote URLs)

# Retention
retention:
  keep_days: 30
  action: archive               # archive | delete
```

## 6. Weaviate Integration

NSDN uses Weaviate as the **Semantic Engine**. It runs alongside SQLite (State Manager) to provide semantic deduplication, interest-based pre-filtering, and vector clustering.

**Architecture:**
- **SQLite**: OLTP. Tracks state (`scored`, `processed`), exact GUID deduplication, edition history.
- **Weaviate**: OLAP. Stores embeddings of `title + summary`. Handles semantic dedup and interest matching.

**Collection Schema (`NSDNEntries`):**

```python
client.collections.create(
    name="NSDNEntries",
    vector_config=Configure.Vectors.text2vec_ollama(
        api_endpoint="http://ollama:11434",
        model="qwen3-embedding:8b"
    ),
    properties=[
        Property(name="guid", data_type=DataType.TEXT, skip_vectorization=True),
        Property(name="title", data_type=DataType.TEXT, skip_vectorization=True),
        Property(name="summary", data_type=DataType.TEXT, skip_vectorization=True),
        Property(name="source_name", data_type=DataType.TEXT, skip_vectorization=True),
        Property(name="published_at", data_type=DataType.TEXT, skip_vectorization=True),
        Property(name="semantic_text", data_type=DataType.TEXT), # Vectorized payload
    ]
)
```

**Embedding Strategy:**
The `semantic_text` property is a concatenation of `title` and `summary`. Weaviate's `text2vec-ollama` module generates the vector on ingest.
## 7. Database Schema (SQLite)

```sql
CREATE TABLE sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,           -- "rss", "hackernews", "reddit", ...
    name TEXT NOT NULL,
    source_config TEXT,                  -- JSON blob of source-specific config
    UNIQUE(source_type, name)
);

CREATE TABLE entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    guid TEXT UNIQUE NOT NULL,           -- unique ID for deduplication
    title TEXT NOT NULL,
    summary TEXT,
    content TEXT,
    link TEXT,
    published_at TEXT,                   # ISO 8601
    author TEXT,
    tags TEXT,                           -- JSON array of tags
    images TEXT,                         -- JSON array of image URLs
    score REAL,                          # NULL = unscored
    kept BOOLEAN DEFAULT 0,              # 1 = passed filter
    processed_in_edition TEXT,           # date string of edition it appeared in
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

CREATE TABLE editions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,                  # ISO 8601 timestamp
    slot TEXT NOT NULL,                  # "morning" | "afternoon" | "evening"
    markdown_path TEXT,
    html_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Deduplication:** Entries are deduplicated by `guid`. Re-running extract won't duplicate.

## 8. Pipeline Details

### 8.1 Extract (`nsdn extract`)

1. Read `sources` from config
2. For each source config, instantiate via `get_source(type)` from the registry
3. Call `source.fetch()` → `list[FeedEntry]`
4. **Exact Dedup:** Check SQLite by GUID. Skip if exists.
5. **Semantic Dedup:** For new entries, query Weaviate for similar vectors (title+summary). If cosine similarity > 0.95 to an existing entry, discard.
6. **Ingest:** Insert surviving entries into SQLite AND Weaviate.
7. Log: number of new entries per source.

**Edge cases handled:**
- Source fetch failure (skip source, continue with others, log error)
- Malformed entries (skip with warning)
- Missing guid (source must provide one; fallback is hash of title+link)
- Timeout per source (configurable, default 10s)
- Rate limiting (per-source `rate_limit` config, backoff on 429)
- Offline resilience (if source is down, entries aren't lost; next run retries)

### 8.2 Filter (`nsdn filter`)

**Step 1: Interest Pre-filter (Weaviate)**
Before calling the LLM, query Weaviate with the user's interests to retrieve the top N most relevant unscored entries. This drastically reduces LLM calls by filtering out irrelevant noise semantically.

**Step 2: LLM Scoring**
Two modes for the pre-filtered entries, selected by `filter.mode`:

**Sequential mode** — one LLM call per entry:
- Low context window usage
- Slow for large feeds
- Robust per-item scoring

**Batch mode** — multiple entries per LLM call:
- Faster, fewer LLM calls
- Higher context usage
- Structured output via `invoke_structured()`

**Offline resilience:** If the LLM is down during filter/synthesize, the pipeline logs a warning and stops. Entries remain unscored. Next `nsdn run` retries them automatically. No data loss.

**Batch mode** — multiple entries per LLM call:
- Faster, fewer LLM calls
- Higher context usage
- Structured output via `invoke_structured()`

```
Group unscored entries into batches of N:
  prompt = format_batch(entries_batch, interests)
  response = llm.invoke_structured(prompt, ScoreBatchSchema, system=FILTER_SYSTEM_PROMPT)
  For each item in response:
    entry.score = item.score
    entry.kept = item.score >= threshold
```

**Pydantic schema for batch structured output:**

```python
class EntryScore(BaseModel):
    entry_id: str       # guid
    score: int          # 0-10
    reason: str         # one-line justification

class ScoreBatch(BaseModel):
    scores: list[EntryScore]
```

**Filter system prompt:**

```
You are a ruthless content filter. Rate each post from 0 to 10 based on
its technical depth and relevance to the user's interests. Be strict —
most posts should score below 7. Only score 7+ for posts with substantive,
actionable, or intellectually stimulating content.

User interests: {interests}
```

### 8.3 Synthesize (`nsdn synthesize`)

Two-step process: **Cluster → Write**. Divide et impera — the LLM never has to both group and write in one pass.

#### Step 1: Cluster

1. Query SQLite: `SELECT * FROM entries WHERE kept=1 AND processed_in_edition IS NULL`
2. Send all kept entries (titles + summaries) to LLM for topic labeling
3. Parse labels, group entries by topic

**Cluster prompt:**

```
Assign a single topic label to each entry below. Use 3-5 distinct labels total.
Entries about the same topic must share the same label.
Respond ONLY with valid JSON: {"entry_guid": "topic_label", ...}

Entries:
{format_entries(entries)}
```

**Structured output schema:**

```python
class ClusterLabels(BaseModel):
    labels: dict[str, str]  # guid → topic_label
```

#### Step 2: Write

Configurable via `synthesize.mode: "llm" | "raw"`.

**Mode A — `llm` (Synthesized):**

1. For each topic group, feed entries to the editor LLM
2. Assemble topic sections into complete Markdown journal
3. Write to `output/journal/YYYY-MM-DD-{slot}.md`
4. Mark entries as processed: `UPDATE entries SET processed_in_edition = ?`

**Editor system prompt:**

```
You are the editor of a highly technical, minimalist journal called NSDN
(No Social Detox News). Synthesize the following posts into a cohesive
journal section on the topic: "{topic}".

Rules:
- Extract core insights — do not paraphrase, distill
- Write in a dry, precise tone. No clickbait, no hype language
- Include original links as references
- 1-2 paragraphs max per section
- No intro or outro text — just the section content
```

If there are many entries, process topic groups sequentially. Assemble into a single Markdown file with `## {topic}` headers.

**Mode B — `raw` (Passthrough):**

No LLM calls after clustering. Clustering (Step 1) still runs to group by topic, but the actual content is the original text.

Sub-mode controlled by `synthesize.raw_content: "summary" | "truncated" | "full"`.

**Sub-mode `summary`:** Use `entry.summary` only.

```markdown
## {topic}

### {entry.title}
> {entry.summary}
— via {entry.source_name} — [{link}]({entry.link})
```

**Sub-mode `truncated`:** Use `entry.content` truncated to `synthesize.raw_max_chars` chars (default 2000), with ellipsis and link for the rest.

```markdown
## {topic}

### {entry.title}
{entry.content[:raw_max_chars]}...
[continue reading...]({entry.link})
— via {entry.source_name}
```

**Sub-mode `full`:** Use `entry.content` in full, no truncation.

```markdown
## {topic}

### {entry.title}
{entry.content}
— via {entry.source_name} — [{link}]({entry.link})
```

All sub-modes: assemble into `output/journal/YYYY-MM-DD-{slot}.md` with `## {topic}` headers, mark entries as processed.

**Tradeoffs:**
| | `llm` | `raw:summary` | `raw:truncated` | `raw:full` |
|--|--|--|--|--|
| LLM cost | cluster + write | cluster only | cluster only | cluster only |
| Prose quality | cohesive, distilled | mixed, short | mixed, medium | mixed, full |
| Edition size | small | small | medium (capped) | large |
| User follow-up | refs in text | link per entry | link per truncated entry | link per entry |

### 8.4 Render (`nsdn render`)

**Pipeline:**

```
entries + designer  →  designer.render_edition()  →  Markdown  →  mistune.render()  →  HTML body  →  designer.template  →  .html
```

1. Load designer from config: `designer = get_designer(config.output.designer)(config)`
2. Designer assembles Markdown: `md = designer.render_edition(entries_by_topic, date, slot)`
3. Render Markdown → HTML via `mistune`
4. Build context: `ctx = designer.get_context(html, date, slot)`
5. Render Jinja2 template: `designer.get_template_path()`
6. Write HTML to `output/journal/YYYY-MM-DD-{slot}.html`

**Base template** (`templates/pico.html`):

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{{ title }}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  {% if inline_css %}
  <style>{{ css }}</style>
  {% else %}
  <link rel="stylesheet" href="{{ css_url }}">
  {% endif %}
</head>
<body>
  <main class="container">
    <header>
      <h1>{{ title }}</h1>
      <time datetime="{{ date }}">{{ date }}</time>
    </header>
    {{ content | safe }}
  </main>
</body>
</html>
```

**Template context** (built by `designer.get_context()`):
- `title` — "NSDN — {date} ({slot})"
- `date` — ISO date string
- `content` — rendered Markdown (via `mistune`), passed as HTML
- `css` — inline CSS string (when designer provides it)
- `css_url` — CSS URL (when designer uses linked CSS)
- `inline_css` — boolean (true when `get_css()` returns non-empty)

**Image handling:**

Images from sources are rendered inline in the Markdown during synthesis. For `raw` mode, the first image (`entry.images[0]`) is placed above the entry content:

```markdown
### {entry.title}

![{entry.title}]({entry.images[0]})

{entry.summary or entry.content}
```

For `llm` mode, the LLM receives image URLs in the prompt and may reference them in its output. The Markdown renderer converts `![alt](url)` to `<img>` tags.

**Image strategy — remote URLs (default):**
Images are referenced by their original URL. The browser fetches them at render time. Zero storage cost, but the image must remain online.

**Image strategy — local cache (optional):**
When `output.cache_images: true`, images are downloaded to `output/journal/assets/` and referenced relatively:

```
output/journal/
  2025-01-15-morning.html
  2025-01-15-morning.md
  assets/
    abc123.jpg
```

Filename is `hash(image_url)` to deduplicate across editions. Configured via `output.cache_images`.

### 8.5 Serve (`nsdn serve`)

```python
python3 -m http.server 8080 --directory /path/to/output/journal
```

Wrapped in a CLI command. Optionally managed via systemd service file.

### 8.6 Full Run (`nsdn run`)

Executes the full pipeline: extract → filter → synthesize → render. Intended for cron/systemd invocation.

## 9. LLM Integration

The project ships with its own copy of the `LLMProvider` ABC and implementations (from MilleniumAI). No external dependency on MilleniumAI — self-contained. A factory function constructs the appropriate provider from config:

```python
def get_llm_provider(config: dict) -> LLMProvider:
    provider = config["llm"]["provider"]
    if provider == "llama_server":
        return LlamaServerProvider(
            model=config["llm"].get("model")
        )  # LLAMA_SERVER_URL from env
    elif provider == "llama_cpp":
        return LlamaCppProvider(
            model_path=config["llm"]["model_path"],
            n_ctx=config["llm"].get("n_ctx", 16384),
            n_gpu_layers=config["llm"].get("n_gpu_layers", 999),
            n_threads=config["llm"].get("n_threads"),
        )
    elif provider == "ollama":
        return OllamaProvider(
            model=config["llm"].get("model", "qwen2.5:3b"),
            host=config["llm"].get("host", "http://localhost:11434"),
        )
```

**Environment variables:** `LLAMA_SERVER_URL`, `OLLAMA_API_KEY`, etc.

## 10. Scheduling

**Option A — Cron:** Simple, no daemon needed.

```cron
0 8,13,19 * * * cd /path/to/nsdn && python -m nsdn run >> /var/log/nsdn.log 2>&1
```

**Option B — Systemd timer:** More observable, better logging.

```ini
# nsdn.service
[Service]
Type=oneshot
ExecStart=/usr/bin/python -m nsdn run
WorkingDirectory=/path/to/nsdn

# nsdn.timer
[Timer]
OnCalendar=08:00,13:00,19:00
Persistent=true
```

The CLI exposes `nsdn generate-cron` and `nsdn generate-systemd` helper commands.

## 11. Dependencies

```toml
[project]
dependencies = [
    "feedparser>=6.0",
    "pyyaml>=6.0",
    "jinja2>=3.1",
    "mistune>=3.0",       # Markdown rendering
    "click>=8.1",         # CLI framework
    "pydantic>=2.0",
    "weaviate-client>=4.0", # Semantic engine
    # LLM providers (optional, installed per need):
    # "llama-cpp-python",
    # "ollama",
]
```

The LLM provider code is shipped with NSDN (copied from MilleniumAI). No external dependency.

## 12. Design Decisions & Tradeoffs

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Pluggable sources | EntrySource ABC + registry | New sources (API, scraping, etc.) without touching pipeline code |
| Pluggable designers | PageDesigner ABC + registry | New journal styles without touching render code |
| Hybrid Storage | SQLite + Weaviate | SQLite for state/OLTP, Weaviate for semantic dedup/filtering |
| SQLite over files | SQLite | Deduplication, scoring state, edition tracking in one place |
| Batch + sequential filter | Both, configurable | Lets users choose speed vs. accuracy based on their hardware |
| YAML config | YAML | Human-readable, standard for CLI tools |
| Jinja2 for templates | Jinja2 | Lightweight, no build step, full control over output |
| Click for CLI | Click | Clean subcommands, auto-generated help |
| LLMProvider (copied) | Self-contained | No external dependency, copy from MilleniumAI, battle-tested code |
| Markdown intermediate | Yes | Inspectable output, easy to debug synthesis quality |
| No web framework | Python http.server | Zero dependencies, single file output, no auth needed (local network) |

## 13. Future Considerations (Not in v1)

- **AI Designer** — LLM agent that generates CSS + Jinja2 templates from natural language prompts (e.g., "minimalist newspaper style", "dark mode tech blog"). Would plug into `PageDesigner` registry as a dynamic designer. The agent produces `style.css` + `template.html` pairs, validated and cached. Users iterate by refining the prompt.
- **Email/Telegram delivery** — push editions instead of pull
- **Feedback loop** — user rates editions, LLM learns preferences
- **Multi-user profiles** — separate configs per user
- **RSS feed discovery** — suggest feeds based on interests
- **Archive browsing** — list past editions with search
- **Authentication** — if exposed beyond local network

## 14. UX & Operational Improvements

### Retention & Archiving
**Problem:** SQLite grows indefinitely. After months, queries slow down and the DB bloats.
**Solution:** Configurable retention policy. `nsdn run` automatically archives old processed entries.

```yaml
retention:
  keep_days: 30
  action: archive  # archive (keep in DB but hidden from queries) | delete
```
**Interaction:** `nsdn archive --keep 30d` or automatic during `run`. Keeps the DB lean without losing history.

### Dry-Run Mode
**Problem:** Tuning `score_threshold` or interests is guesswork. Running `nsdn run` commits entries to an edition, making it hard to adjust.
**Solution:** `nsdn run --dry-run` fetches, scores, and previews without marking entries as processed.

**Interaction:**
```
$ nsdn run --dry-run
[extract] Fetched 24 new entries from 3 sources.
[filter] Scored 24 entries. Kept: 8/24 (threshold: 7).
[cluster] Topics: AI Research (4), Linux Kernel (2), Security (2).
[preview] Would generate "2024-05-20-morning.md".
[Dry run complete. No entries marked as processed.]
```

### Offline Resilience
**Problem:** LLM server down at 8 AM → cron job fails → entries lost or skipped.
**Solution:** Pipeline detects LLM unavailable → logs warning → leaves entries unscored. Next run retries them. Entries are never lost or prematurely marked processed.

### Edition Preview
**Problem:** Opening the directory listing isn't a clean UX.
**Solution:** `nsdn serve` defaults to the latest edition. `nsdn serve --open` auto-opens the browser on `--dev` mode.

### Source Rate Limiting
**Problem:** Aggressive fetching triggers 429s from HN, Reddit, etc.
**Solution:** Per-source rate limits in config. Extract waits between sources.

```yaml
sources:
  - type: hackernews
    name: "HN Show HN"
    rate_limit: 1 req/5s
```

### Inline CSS
**Problem:** External CSS links make network requests, defeating the "zero network" goal.
**Solution:** CSS is inlined into the HTML by default. Configurable.

```yaml
output:
  inline_css: true  # true | false
```

### Score Distribution Stats
**Problem:** LLM scoring drifts over time. Too strict or too loose.
**Solution:** `nsdn stats` shows score histograms per source.

```
$ nsdn stats
Source          | Avg Score | Kept (%) | Entries
----------------|-----------|----------|--------
Hacker News     | 5.2       | 18%      | 142
LWN NetDev      | 7.1       | 64%      | 89
```

### Cluster Strategy (Draft)
**Single-pass:** One LLM call labels all kept entries. Fast, but context-heavy for 30+ entries.
**Two-tier:** Pass 1 assigns broad categories (e.g., "AI", "Systems", "Security"). Pass 2 refines within category. Slower, but handles large batches cleanly.
**Decision:** Implement single-pass first. Add two-tier if context limits are hit.

## 15. Implementation Plan

Phase 1 — Foundation:
1. Project scaffold (pyproject.toml, directory structure)
2. Config loading (YAML → Pydantic model)
3. Source abstraction: EntrySource ABC, FeedEntry model, registry
4. Designer abstraction: PageDesigner ABC, registry
5. SQLite schema + db.py
6. Weaviate integration: Collection schema, semantic dedup logic
7. RSS source implementation (feedparser → FeedEntry)
8. Extract pipeline (orchestrates all sources → SQLite + Weaviate)

Phase 2 — LLM Pipeline:
9. Copy LLMProvider + implementations from MilleniumAI → `src/llm.py`
10. Filter: sequential mode
11. Filter: batch mode with structured output
12. Synthesize: cluster step (topic labeling)
13. Synthesize: editor step (write journal sections) + raw mode

Phase 3 — Presentation:
14. Render: designer.load() → render_edition() → mistune → Jinja2
15. Pico designer + template
16. Serve: HTTP server wrapper

Phase 4 — Operations:
17. CLI polish (click commands, error handling)
18. Cron/systemd generation helpers
19. Logging and error resilience

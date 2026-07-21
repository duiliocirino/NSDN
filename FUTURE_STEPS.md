## Future Steps for NSDN

### **Completed**
- [x] **Structured Image Extraction** — Priority-based `_extract_images()` (gallery → media_metadata, image → i.redd.it, video → secure_media, fallback → i.redd.it thumbnail only). external-preview.redd.it rejected (blocked). Test suite: 30/30 pass.
- [x] **Color Configuration System** — Configurable palette in `config.py`, CSS variables in `generator.py`, `preview_colors.py` script.
- [x] **Topic Header Enhancement** — Newspaper-style `.topic-header` CSS with `::before`/`::after` pseudo-elements.
- [x] **Evaluator Criticality** — Enhanced scoring scale (1-10) with explicit penalties in `EVALUATE_TEXT_SYSTEM_PROMPT`.
- [x] **PDF Margin Fix** — `@page { margin: 0 }` CSS instead of ignored `presentation` dict.
- [x] **Clustering Bug Fix** — Empty topic filtering with "General" fallback in `llm_cluster.py`.
- [x] **VLM Prompt Fix** — `EVALUATE_VLM_SYSTEM_PROMPT` now used (was hardcoded prompt).
- [x] **Hide Broken Images** — `onerror="this.style.display='none'"` in hero.py + grid.py.
- [x] **Evaluator Criticality** — Strict scoring scale (1-10) with explicit penalties and VLM prompt alignment.
- [x] **Mobile/Desktop Mode** — Dual-mode rendering (CSS Variant approach). `ViewportMode` config, mode-aware layouts (stacked hero, 1-col grid, top-border sidebar), separate mobile cover/edition PDFs. Mobile PDFs use 375px viewport.
- [x] **Multi-Page VLM Evaluation** — PDF→images via `pypdfium2`, all pages passed to VLM for holistic assessment. Detects cut images, awkward page breaks, missing content on pages 2-3.
- [x] **Mobile Cover Generation** — `generate_cover(mode)` renders mode-aware hero/grid for both desktop and mobile covers.
- [x] **Hero Layout Fix** — Mobile hero uses `display: block` instead of flex to prevent WeasyPrint height-calculation bugs and content overlap.
- [x] **Mobile Page-Cut Fix** — `break-inside: avoid` on grid items, hero articles, and sidebar items. `max-height: 360px` on mobile stacked images. Prevents images from splitting across pages.
- [x] **Automated Delivery** — `DeliveryTarget` ABC with `TelegramDelivery` (Bot API sendDocument) and `EmailDelivery` (SMTP). Registry pattern matching existing extension points. `nsdn run --deliver` (integrated) and `nsdn deliver --edition <path>` (standalone). `${ENV_VAR}` resolution in config loader for sensitive credentials.
- [x] **Scheduled Runs (Auto-Publishing)** — `scripts/setup_schedule.sh` generates systemd service + timer with `.env` loading. Cron alternative documented. Runs `nsdn run --deliver` at configured schedule times.
- [x] **RSS/Atom Source** — `RssSource` using `feedparser`. Supports time filtering, image extraction (media:content, enclosure, img tags), dual tag extraction (`categories` + `tags`), None-safe content access. Registry-registered as `"rss"`.
- [x] **RSS Retry Logic** — Exponential backoff on 429 rate-limited feeds, configurable `max_retries` and `retry_delay`.
- [x] **Browser Cookie Auth for Reddit** — `cookie_utils.py` reads Reddit session cookies from Firefox profile (`cookies.sqlite`) at fetch time. Bypasses 429 rate limits on `.json` API. Falls back to OAuth credentials if cookies unavailable. `use_cookies` config option (default `True`).
- [x] **Weaviate URL Parsing Fix** — Replaced broken `split(":")` URL parsing with `urlparse`. Corrected default port to `8050`.
- [x] **Inter-Source Delay** — 1s delay between sources in extract pipeline to avoid hammering feed providers.

### **High Priority (Current Focus)**
1. **Weaviate End-to-End Verification**
   - Location: `src/nsdn/vector.py`, `config/nsdn.yaml`
   - Action: Start Weaviate container, verify connection, test semantic dedup and search.
   - Rationale: URL parsing is fixed but never tested against a running instance.

2. **X/Twitter Source (via RSS Bridge)**
   - Location: `src/nsdn/sources/x.py` (new file) or RSS config pointing to bridge
   - Action: Use RSS bridge (rsshub.app or similar) to fetch X user timelines as RSS, consumed by RSS source.
   - Rationale: X API v2 free tier is too limited; RSS bridge avoids API keys entirely.
   - Depends on: RSS source implementation

### **Medium Priority (Next Features)**
1. **Support Multiple Drafts per Topic**
   - Location: `src/nsdn/newspaper/component.py`
   - Action: Allow LLM to generate multiple drafts per topic and select the best one.
   - Rationale: Improve layout quality through iteration and selection.

2. **Accept Multiple Images per Entry**
   - Location: `src/nsdn/newspaper/generator.py`
   - Action: Modify image handling to include multiple images per entry if available.
   - Rationale: Enhance topic pages with richer visual content.

3. **Add Text-to-Image Generation for Topics with No Images**
   - Location: `src/nsdn/newspaper/generator.py`
   - Action: Use a secondary model to generate images based on the designer's prompt.
   - Rationale: Enhance visual appeal for topics lacking images.

### **Lower Priority (Future Enhancements)**
1. **Implement Registry Validation for Highlight Selectors**
   - Location: `src/nsdn/newspaper/selectors.py`
   - Action: Add `issubclass(cls, HighlightSelector)` check in `register_selector`.
   - Rationale: Ensure only valid selectors are registered.

2. **Add Additional Highlight Selectors (e.g., editorial variety)**
   - Location: `src/nsdn/newspaper/selectors.py`
   - Action: Extend `HighlightSelector` with new strategies.
   - Rationale: Increase flexibility in cover design.

3. **Implement PullQuote and StatBox Components**
   - Location: `src/nsdn/newspaper/layouts/pullquote.py`, `src/nsdn/newspaper/layouts/statbox.py`
   - Rationale: Add advanced layout features for professionalism.

4. **Add HackerNews Source**
   - Location: `src/nsdn/sources/hackernews.py`
   - Rationale: Support additional content sources.

5. **Integrate DebugEmitter for Structured Logging in All Strategies**
   - Location: `src/nsdn/newspaper/component.py`, `src/nsdn/newspaper/template.py`
   - Action: Ensure `DebugEmitter` is initialized and used consistently in all strategies.
   - Rationale: Improve debugging and artifact storage for all strategies.

---

**Notes:**
- All steps are derived from previous discussions and align with the project's registry and strategy patterns.
- File paths are based on the current project structure (e.g., `component.py`, `template.py`, `evaluator.py`).
- Lower-priority steps are marked for future milestones (e.g., V2 roadmap).

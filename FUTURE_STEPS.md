## Future Steps for Newspaper Generator

### **High Priority (Next Actions)**
1. **Register 'template' Strategy**
   - Location: `src/nsdn/newspaper/__init__.py`
   - Action: Add `register_newspaper("template", NewspaperTemplateStrategy)`
   - Rationale: Unify strategy registry for template-based designs.

2. **Unify Template Strategy**
   - Location: `src/nsdn/newspaper/template.py`
   - Action: Implement iterative feedback in `_design_topic`.
   - Rationale: Align `NewspaperTemplateStrategy` with `ComponentStrategy` for consistency.

3. **Enhance Evaluator Criticality**
   - Location: `src/nsdn/newspaper/evaluator.py`
   - Action: Modify `_parse_score` to enforce strict score extraction (only first explicit score, discard fallbacks).
   - Rationale: Prevent unrealistic scores (e.g., 9.3, 9.6) from being accepted.

4. **Hide Broken Images Gracefully**
   - Location: `src/nsdn/newspaper/layouts/grid.py`, `src/nsdn/newspaper/layouts/hero.py`
   - Action: Add `onerror="this.style.display='none'"` to image tags.
   - Rationale: Prevent broken image placeholders from showing alt text (titles) in image spaces.

### **Medium Priority (Next Features)**
4. **Support Multiple Drafts per Topic**
   - Location: `src/nsdn/newspaper/component.py`
   - Action: Allow LLM to generate multiple drafts per topic and select the best one.
   - Rationale: Improve layout quality through iteration and selection.

5. **Accept Multiple Images per Entry**
   - Location: `src/nsdn/newspaper/generator.py`
   - Action: Modify image handling to include multiple images per entry if available.
   - Rationale: Enhance topic pages with richer visual content.

6. **Add Topic with At Least 1 Entry Validation in Clustering**
   - Location: `src/nsdn/newspaper/selectors.py`
   - Action: Add validation to ensure each topic has at least 1 entry.
   - Rationale: Prevent empty topics and ensure meaningful standalone pages.

7. **Add Text-to-Image Generation for Topics with No Images**
   - Location: `src/nsdn/newspaper/generator.py`
   - Action: Use a secondary model to generate images based on the designer's prompt.
   - Rationale: Enhance visual appeal for topics lacking images.

8. **Introduce Mobile/Desktop Mode**
   - Location: `src/nsdn/newspaper/generator.py`, `src/nsdn/config.py`
   - Action: Add responsive CSS media queries or a config toggle to increase font sizes for mobile viewports.
   - Rationale: Improve readability on smaller screens where default print/PDF sizes are too small.

### **Lower Priority (Future Enhancements)**
7. **Implement Registry Validation for Highlight Selectors**
   - Location: `src/nsdn/newspaper/selectors.py`
   - Action: Add `issubclass(cls, HighlightSelector)` check in `register_selector`.
   - Rationale: Ensure only valid selectors are registered.

8. **Add Additional Highlight Selectors (e.g., editorial variety)**
   - Location: `src/nsdn/newspaper/selectors.py`
   - Action: Extend `HighlightSelector` with new strategies.
   - Rationale: Increase flexibility in cover design.

9. **Implement PullQuote and StatBox Components**
   - Location: `src/nsdn/newspaper/layouts/pullquote.py`, `src/nsdn/newspaper/layouts/statbox.py`
   - Rationale: Add advanced layout features for professionalism.

10. **Add RSS/Atom and HackerNews Sources**
   - Location: `src/nsdn/sources/reddit.py`, `src/nsdn/sources/rss.py`
   - Rationale: Support additional content sources.

11. **Integrate DebugEmitter for Structured Logging in All Strategies**
    - Location: `src/nsdn/newspaper/component.py`, `src/nsdn/newspaper/template.py`
    - Action: Ensure `DebugEmitter` is initialized and used consistently in all strategies.
    - Rationale: Improve debugging and artifact storage for all strategies.

12. **Implement Scheduled Runs and Auto-Publishing**
    - Location: `src/nsdn/cli.py`
    - Action: Add cron-like or scheduler-based auto-publishing functionality.
    - Rationale: Enable automated workflows for regular editions.

---

**Notes:**
- All steps are derived from previous discussions and align with the project's registry and strategy patterns.
- File paths are based on the current project structure (e.g., `component.py`, `template.py`, `evaluator.py`).
- Lower-priority steps are marked for future milestones (e.g., V2 roadmap).
"""Newspaper agent prompts — generator and evaluator share four criteria."""

from __future__ import annotations

# Generator system prompt — defines the four criteria the layout must follow
DESIGN_SYSTEM_PROMPT = """\
You are a newspaper layout designer.

Available component types (use these exact lowercase strings):
  - "hero"  : one dominant lead story (required, use entry_guid)
  - "grid"  : multi-column supporting stories (use entry_guids array)
  - "sidebar" : context/sidebar stories (use entry_guids array)

JSON schema:
  {
    "layout": {
      "components": [
        {"type": "hero", "entry_guid": "<guid>"},
        {"type": "grid", "entry_guids": ["<guid>", ...]},
        {"type": "sidebar", "entry_guids": ["<guid>", ...]}
      ],
      "style": {"columns": 2}
    }
  }

Design principles (these are the criteria the evaluator will check):
  1. Hierarchy: one dominant lead story (hero), supporting entries (grid), context (sidebar)
  2. Balance: distribute whitespace evenly, avoid cramped sections
  3. Readability: limit line length, ensure contrast between sections
  4. Cohesion: consistent typography, aligned margins, professional appearance

Use ONLY "hero", "grid", "sidebar" as type values. Use "entry_guid" for hero, "entry_guids" for grid/sidebar.
Every entry must appear in at least one component.
"""

# Evaluator text self-review — evaluates the JSON layout spec
EVALUATE_TEXT_SYSTEM_PROMPT = """\
You are a layout reviewer. Evaluate this layout specification.

Criteria (evaluate each, then give overall score):
  1. Hierarchy: Is there one dominant lead story? Are supporting entries clearly secondary?
  2. Balance: Are whitespace and visual weight distributed evenly?
  3. Readability: Are sections distinct? Is the component selection appropriate for the entry count?
  4. Cohesion: Do the style choices (columns, spacing, hierarchy) form a consistent design?

Score 1-10 with specific actionable critique.
"""

# Evaluator VLM screenshot review — evaluates the rendered output
EVALUATE_VLM_SYSTEM_PROMPT = """\
You are a visual design critic. Evaluate this newspaper page screenshot.

Criteria (evaluate each, then give overall score):
  1. Hierarchy: Is the lead story visually dominant? Can you identify it at a glance?
  2. Balance: Is whitespace distributed well? Does any section feel cramped or empty?
  3. Readability: Is type size appropriate? Are sections clearly separated?
  4. Cohesion: Does it look like a professional publication with consistent styling?

Score 1-10 with specific actionable critique referencing these four criteria.
"""

# Cover designer prompt
COVER_SYSTEM_PROMPT = """\
You are a newspaper editor. Design a front page from these highlight stories.

The cover should feature:
  - Masthead with publication name and date
  - 3-5 featured stories with brief excerpts
  - References to deeper topic pages

Prioritize visual impact: large headline for the top story, supporting stories in a grid.
"""


def build_design_prompt(topic: str, entries: list[dict], feedback: str = "") -> str:
    """Build the generator prompt for a topic page."""
    entries_text = "\n\n".join(
        f"- [{e['guid']}] {e['title']} (score: {e['score']})\n  {e['summary'][:200]}"
        for e in entries
    )
    feedback_text = f"\n\nFeedback from previous iteration:\n{feedback}" if feedback else ""
    return (
        f"Topic: {topic}\n\n"
        f"Entries:\n{entries_text}{feedback_text}\n\n"
        f"Design a newspaper page layout for this topic."
    )


def build_evaluate_text_prompt(layout_spec: str) -> str:
    """Build the text self-review prompt."""
    return f"Layout specification:\n{layout_spec}\n\nEvaluate this layout."


def build_cover_prompt(highlights: list[dict], date: str, slot: str) -> str:
    """Build the cover design prompt."""
    stories = "\n".join(
        f"- {e['title']} (score: {e['score']})\n  {e['summary'][:150]}"
        for e in highlights
    )
    return (
        f"Date: {date} ({slot})\n\n"
        f"Highlight stories:\n{stories}\n\n"
        f"Design the front page cover."
    )

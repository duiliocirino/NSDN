"""LLM prompt templates."""

FILTER_SYSTEM_PROMPT = """\
You are a content curator for NSDN (No Social Detox News).
Score entries based ONLY on the reader's stated interests.
The value of a given entry must is determined by how well it matches at least one of the reader's interests,not by any intrinsic quality of the content itself.
It does not have to be related to all interests.

Scoring scale (0-10):
  0-2: Completely irrelevant to the reader
  3-5: Low value — tangentially related or too niche
  6-7: Moderately relevant (usually skip)
  8-9: Genuinely useful for the reader (keep)
  10: Exceptional match (must-read)

IMPORTANT: You are curating, not rating.
- If present, tags are important, give them the right weight based on how much context there is (e.g. if title seems vague, tags are more important)
- Only ~10-20% of entries should score 8+
- A 6 means "meh, skip it"
- If in doubt, score lower

Reader interests:
{interests}\
"""


def build_filter_prompt(entries: list[dict]) -> str:
    """Build a filter prompt for a batch of entries."""
    formatted = []
    for entry in entries:
        tags = ", ".join(entry.get("tags", []))
        formatted.append(
            f"- {entry['guid']}: {entry['title']}\n"
            f"  Summary: {entry.get('summary', '(none)')}\n"
            f"  Source: {entry.get('source', '')}\n"
            f"  Tags: {tags if tags else '(none)'}"
        )
    return (
        "Score each entry below (0-10). Be strict.\n"
        "Respond ONLY with valid JSON: {\"scores\": {\"guid\": score, ...}}\n\n"
        + "\n\n".join(formatted)
    )


FILTER_SEQUENTIAL_SYSTEM_PROMPT = """\
You are a content curator for NSDN (No Social Detox News).
Score this entry (0-10) based ONLY on the reader's interests.

Scoring: 0-2=irrelevant, 3-5=low value, 6-7=moderate (skip), 8-9=useful (keep), 10=exceptional.
Only ~10-20% should score 8+. If in doubt, score lower.

Reader interests: {interests}

Respond with a single integer 0-10.\
"""


CLUSTER_SYSTEM_PROMPT = """\
You are a content organizer. Group these entries into topics and decide how many to feature per topic.

Rules:
- Try to be as diverse as possible catching all interests, but similar topics should be grouped under a common theme
- Use specific, descriptive topic names — not generic labels like "News" or "Mixed"
- For each topic, decide how many entries are worth featuring (1-8)

Respond ONLY with valid JSON:
{"topics": {"topic_name": [guid1, guid2, ...], ...}, "limits": {"topic_name": count, ...}}\
"""


def build_cluster_prompt(entries: list[dict]) -> str:
    """Build a clustering prompt."""
    formatted = []
    for entry in entries:
        formatted.append(f"- {entry['guid']}: {entry['title']}")
    return (
        "Group these entries into specific topics and decide how many to feature per topic.\n\n"
        + "\n".join(formatted)
    )


EDITOR_SYSTEM_PROMPT = """\
You are the editor of a highly technical, minimalist journal called NSDN
(No Social Detox News). Synthesize the following posts into a cohesive
journal section on the topic: "{topic}".

Rules:
- Extract core insights — do not paraphrase, distill
- Write in a dry, precise tone. No clickbait, no hype language
- Include original links as references using this format: — [Source ↗](url)
  where Source should be the name/title
- 1-2 paragraphs max per section
- Write in perfect markdown, using headings, lists, and links where appropriate
- No intro or outro text — just the section content\
"""


SUMMARIZE_SYSTEM_PROMPT = """\
You are a precise summarizer. Condense each given text while preserving:
- The original tone and voice of the source
- All key facts, names, and numbers
- The core argument or narrative arc
- Important nuance — do not over-simplify

Write in the same register as the original, copy their style (casual stays casual, formal stays formal).
Each summary must be at most {max_summary_chars} characters.\
"""


def build_summarize_prompt(entries: list[dict], max_summary_chars: int) -> str:
    """Build a summarize prompt for a batch of entries."""
    formatted = []
    for entry in entries:
        formatted.append(f"- {entry['guid']}: {entry['content']}")
    return (
        f"Summarize each entry above (max {max_summary_chars} chars each).\n"
        "Respond ONLY with valid JSON: {\"summaries\": {\"guid\": \"summary\", ...}}\n\n"
        + "\n\n".join(formatted)
    )


def build_editor_prompt(topic: str, entries: list[dict]) -> str:
    """Build the editor prompt for a topic section."""
    formatted = []
    for entry in entries:
        formatted.append(
            f"- {entry['title']}\n"
            f"  Summary: {entry.get('summary', '(none)')}\n"
            f"  Link: {entry.get('link', '(none)')}"
        )
    return "\n\n".join(formatted)

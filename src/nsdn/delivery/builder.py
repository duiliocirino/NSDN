"""Build ContentInfo from an edition output directory."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from nsdn.config import DeliveryContentConfig
from nsdn.delivery.base import ContentInfo

logger = logging.getLogger(__name__)

# Matches edition dir names like "2026-05-06-afternoon" or "2026-05-06-morning"
_EDITION_DIR_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)$")


def _parse_dir_name(name: str) -> tuple[str, str]:
    """Extract (date, slot) from an edition directory name.

    Returns ("", "") if the name doesn't match the expected pattern.
    """
    match = _EDITION_DIR_RE.match(name)
    if match:
        return match.group(1), match.group(2)
    return "", ""


def build_content_info(
    edition_dir: Path, content: DeliveryContentConfig
) -> ContentInfo:
    """Assemble delivery content from an edition output directory.

    Discovers PDFs, topics, and generates a caption from the configured
    template.
    """
    date, slot = _parse_dir_name(edition_dir.name)

    # Discover PDFs
    pdf_path = edition_dir / "edition.pdf" if content.include_pdf else None
    mobile_pdf_path = (
        edition_dir / "edition-mobile.pdf" if content.include_mobile_pdf else None
    )

    if pdf_path and not pdf_path.exists():
        logger.warning("Desktop PDF not found: %s", pdf_path)
        pdf_path = None

    if mobile_pdf_path and not mobile_pdf_path.exists():
        logger.warning("Mobile PDF not found: %s", mobile_pdf_path)
        mobile_pdf_path = None

    # Discover topics from the topics/ subdirectory.
    # Topics are flat files (topic-name.pdf, topic-name.html), not subdirectories.
    topics_dir = edition_dir / "topics"
    topic_names: list[str] = []
    if topics_dir.is_dir():
        seen_stems: set[str] = set()
        for f in sorted(topics_dir.iterdir()):
            if f.is_file() and f.suffix in (".pdf", ".html"):
                stem = f.stem
                if stem not in seen_stems:
                    seen_stems.add(stem)
                    topic_names.append(
                        stem.replace("-", " ").replace("_", " ").replace("&", "&")
                    )
        entry_count = len(topic_names)
    else:
        entry_count = 0

    # Build caption
    caption = ""
    if content.include_caption:
        try:
            caption = content.caption_template.format(
                date=date or edition_dir.name,
                slot=slot or "",
                topics=", ".join(topic_names),
                entry_count=entry_count,
            )
        except KeyError as e:
            logger.warning("Unknown placeholder in caption template: %s", e)
            caption = f"NSDN Edition — {date or edition_dir.name}"

    return ContentInfo(
        date=date or edition_dir.name,
        slot=slot,
        topics=topic_names,
        entry_count=entry_count,
        pdf_path=pdf_path,
        mobile_pdf_path=mobile_pdf_path,
        caption=caption,
    )

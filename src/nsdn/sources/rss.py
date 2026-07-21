"""RSS/Atom feed source implementation."""

from __future__ import annotations

import calendar
import logging
import re
from datetime import datetime, timedelta, timezone
from html import unescape

import feedparser

from nsdn.sources.base import EntrySource, FeedEntry
from nsdn.sources import register_source

logger = logging.getLogger(__name__)


class RssSource(EntrySource):
    source_type = "rss"

    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self.url = config.get("url", "")
        self.limit = config.get("limit", 25)
        # Hours to look back (e.g., 24 = last day)
        self.time_filter_hours = config.get("time_filter", 24)

    def validate(self) -> bool:
        try:
            feed = feedparser.parse(self.url)
            if feed.bozo and not feed.entries:
                logger.error("RSS validation failed for %s: malformed feed", self.url)
                return False
            return True
        except Exception as exc:
            logger.error("RSS validation failed for %s: %s", self.url, exc)
            return False

    def _extract_images(self, entry: dict) -> list[str]:
        """Extract images from an RSS/Atom entry.

        Priority:
        1. media:content (common in media-rich feeds)
        2. enclosure type="image/*"
        3. <img> tags in content or summary
        """
        images: list[str] = []

        # 1. media:content
        for media in entry.get("media_content", []):
            if media.get("type", "").startswith("image/") and media.get("url"):
                images.append(media["url"])

        # 2. enclosure
        for enclosure in entry.get("enclosures", []):
            if enclosure.get("type", "").startswith("image/") and enclosure.get("href"):
                images.append(enclosure["href"])

        # 3. <img> tags in content or summary
        content = entry.get("content", [{}])
        text = ""
        if isinstance(content, list) and content:
            text = content[0].get("value", "")
        elif isinstance(content, dict):
            text = content.get("value", "")
        if not text:
            text = entry.get("summary", "")

        img_urls = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', text)
        for url in img_urls:
            if url and url not in images:
                images.append(url)

        return images

    def fetch(self) -> list[FeedEntry]:
        logger.info("Fetching RSS %s (limit=%d, time_filter=%dh)", self.url, self.limit, self.time_filter_hours)
        feed = feedparser.parse(self.url)

        if feed.bozo and not feed.entries:
            logger.warning("Malformed RSS feed: %s", self.url)
            return []

        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=self.time_filter_hours)
        entries: list[FeedEntry] = []

        for item in feed.entries[: self.limit]:
            # Published time — feedparser uses published_parsed or updated_parsed
            published_at = None
            parsed = item.get("published_parsed") or item.get("updated_parsed")
            if parsed:
                published_at = datetime.fromtimestamp(
                    calendar.timegm(parsed), tz=timezone.utc
                )

            # Skip entries older than time_filter
            if published_at and published_at < cutoff:
                continue

            # GUID: prefer explicit <guid>, fall back to <link>, fall back to title hash
            guid = item.get("id") or item.get("link") or f"rss-{hash(item.get('title', ''))}"
            guid = f"rss-{self.name}-{guid}"

            # Content and summary
            content = ""
            contents = item.get("content", [])
            if isinstance(contents, list) and contents:
                content = unescape(contents[0].get("value", ""))
            elif isinstance(contents, dict):
                content = unescape(contents.get("value", ""))
            content = content or item.get("summary", "")

            summary = content[:500] if content else item.get("title", "")

            # Tags from <category>
            tags: list[str] = []
            for cat in item.get("categories", []):
                tag = cat if isinstance(cat, str) else str(cat)
                tags.append(tag)
            tags.append(f"feed:{self.name}")

            entry = FeedEntry(
                source_type=self.source_type,
                source_name=self.name,
                guid=guid,
                title=item.get("title", ""),
                summary=summary,
                content=content,
                link=item.get("link"),
                published_at=published_at,
                author=item.get("author"),
                tags=tags,
                images=self._extract_images(item),
            )
            entries.append(entry)

        logger.info("Fetched %d entries from %s", len(entries), self.url)
        return entries


register_source("rss", RssSource)

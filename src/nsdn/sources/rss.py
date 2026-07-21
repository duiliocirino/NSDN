"""RSS/Atom feed source implementation."""

from __future__ import annotations

import calendar
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from html import unescape

import feedparser

from nsdn.sources.base import EntrySource, FeedEntry
from nsdn.sources import register_source

logger = logging.getLogger(__name__)

# Default User-Agent — Reddit blocks generic feedparser UA.
# A recognizable but browser-like UA avoids rate-limiting.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class RssSource(EntrySource):
    source_type = "rss"

    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self.url = config.get("url", "")
        self.limit = config.get("limit", 25)
        # Hours to look back (e.g., 24 = last day)
        self.time_filter_hours = config.get("time_filter", 24)
        self.user_agent = config.get("user_agent", DEFAULT_USER_AGENT)
        self.max_retries = config.get("max_retries", 2)
        self.retry_delay = config.get("retry_delay", 3)

    def _fetch_feed(self) -> dict:
        """Fetch the feed with retry logic for rate-limited responses."""
        for attempt in range(1, self.max_retries + 1):
            feed = feedparser.parse(self.url, agent=self.user_agent)

            # Success — entries found or valid empty feed
            if feed.entries or (feed.status and feed.status < 400):
                return feed

            status = feed.get("status", 0)
            if status == 429:
                # Rate-limited — back off and retry
                wait = self.retry_delay * attempt
                logger.warning(
                    "RSS %s rate-limited (429), retry %d/%d in %ds",
                    self.url, attempt, self.max_retries, wait,
                )
                time.sleep(wait)
                continue

            # Other errors — return as-is so caller can inspect
            logger.warning("RSS %s returned status %d", self.url, status)
            return feed

        # Exhausted retries — return last result (likely empty)
        logger.error("RSS %s failed after %d retries", self.url, self.max_retries)
        return feed

    def validate(self) -> bool:
        try:
            feed = feedparser.parse(self.url, agent=self.user_agent)
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
        content = entry.get("content") or [{}]
        text = ""
        if isinstance(content, list) and content:
            text = content[0].get("value", "") if isinstance(content[0], dict) else str(content[0])
        elif isinstance(content, dict):
            text = content.get("value", "")
        if not text:
            text = entry.get("summary", "") or ""

        img_urls = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', text)
        for url in img_urls:
            if url and url not in images:
                images.append(url)

        return images

    def fetch(self) -> list[FeedEntry]:
        logger.info("Fetching RSS %s (limit=%d, time_filter=%dh)", self.url, self.limit, self.time_filter_hours)
        feed = self._fetch_feed()

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

            # Content and summary — some feeds return None for content
            content = ""
            contents = item.get("content") or []
            if isinstance(contents, list) and contents:
                content = unescape(contents[0].get("value", ""))
            elif isinstance(contents, dict):
                content = unescape(contents.get("value", ""))
            content = content or item.get("summary", "")

            summary = content[:500] if content else item.get("title", "")

            # Tags from <category> and <tag> — feeds use different fields
            # Atom/RSS 2.0: categories (list of strings or dicts)
            # WordPress/Reddit: tags (list of dicts with 'term' key)
            tags: list[str] = []
            for cat in item.get("categories") or []:
                tag = cat if isinstance(cat, str) else str(cat)
                if tag and tag not in tags:
                    tags.append(tag)
            for tag_obj in item.get("tags") or []:
                term = tag_obj.get("term") if isinstance(tag_obj, dict) else str(tag_obj)
                if term and term not in tags:
                    tags.append(str(term))
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

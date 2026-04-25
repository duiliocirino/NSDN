"""Reddit source implementation."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

from nsdn.sources.base import EntrySource, FeedEntry
from nsdn.sources import register_source

logger = logging.getLogger(__name__)


class RedditSource(EntrySource):
    source_type = "reddit"

    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self.subreddit = config.get("subreddit", "all")
        self.sort = config.get("sort", "hot")  # hot | new | top
        self.limit = config.get("limit", 25)
        self.time_filter = config.get("time_filter", "day")  # hour | day | week | month | year | all
        self.client_id = config.get("client_id", "")
        self.client_secret = config.get("client_secret", "")
        self.user_agent = config.get("user_agent", "NSDN/0.1")

    def validate(self) -> bool:
        try:
            self._fetch_posts()
            return True
        except Exception as exc:
            logger.error("Reddit validation failed for r/%s: %s", self.subreddit, exc)
            return False

    def _auth_headers(self) -> dict[str, str]:
        headers = {"User-Agent": self.user_agent}
        if self.client_id and self.client_secret:
            import base64

            credentials = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"
        return headers

    def _fetch_posts(self) -> list[dict]:
        url = f"https://www.reddit.com/r/{self.subreddit}/{self.sort}.json"
        params = {
            "limit": self.limit,
            "t": self.time_filter,
        }
        resp = requests.get(url, headers=self._auth_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data["data"]["children"]

    def _extract_images(self, post: dict) -> list[str]:
        images: list[str] = []
        # Thumbnail
        thumbnail = post.get("thumbnail", "")
        if thumbnail and not thumbnail.startswith(("self", "default", "icon", "nsfw")):
            images.append(thumbnail)
        # Preview images
        preview = post.get("preview", {})
        if preview:
            first_img = preview.get("images", [{}])[0] if preview.get("images") else {}
            url = first_img.get("url")
            if url:
                images.append(url)
        # Post thumbnail (for link posts)
        if post.get("is_self") is False and post.get("thumb") and not post["thumb"].startswith(("self", "default", "icon", "nsfw")):
            if post["thumb"] not in images:
                images.append(post["thumb"])
        return images

    def fetch(self) -> list[FeedEntry]:
        logger.info("Fetching Reddit r/%s (%s, limit=%d)", self.subreddit, self.sort, self.limit)
        posts = self._fetch_posts()
        entries = []

        for post in posts:
            data = post["data"]
            guid = f"reddit-{self.subreddit}-{data['id']}"

            # Content: selftext for self-posts, body for link posts
            content = data.get("selftext") or data.get("body", "")

            # Summary: first 500 chars of content, or title for link posts
            summary = content[:500] if content else data.get("title", "")

            # Published time
            created_utc = data.get("created_utc")
            published_at = datetime.fromtimestamp(created_utc, tz=timezone.utc) if created_utc else None

            # Link
            url = f"https://reddit.com{data['permalink']}"
            if not data.get("is_self"):
                url = data.get("url", url)

            # Tags
            tags = [f"r/{self.subreddit}"]
            if data.get("link_flair_text"):
                tags.append(data["link_flair_text"])
            if data.get("spoiler"):
                tags.append("spoiler")
                content = "[spoiler] " + content

            entry = FeedEntry(
                source_type=self.source_type,
                source_name=self.name,
                guid=guid,
                title=data["title"],
                summary=summary,
                content=content,
                link=url,
                published_at=published_at,
                author=data.get("author"),
                tags=tags,
                images=self._extract_images(data),
            )
            entries.append(entry)

        logger.info("Fetched %d entries from r/%s", len(entries), self.subreddit)
        return entries


register_source("reddit", RedditSource)

"""Reddit source implementation."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

from nsdn.cookie_utils import get_browser_cookies
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
        # Use browser cookies from Firefox to bypass rate limits
        self.use_cookies = config.get("use_cookies", True)

    def validate(self) -> bool:
        try:
            self._fetch_posts()
            return True
        except Exception as exc:
            logger.error("Reddit validation failed for r/%s: %s", self.subreddit, exc)
            return False

    def _request_kwargs(self) -> dict:
        """Build request kwargs with auth (cookies or OAuth)."""
        kwargs: dict = {
            "headers": {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:152.0) Gecko/20100101 Firefox/152.0"},
            "timeout": 30,
        }

        # Prefer browser cookies if enabled
        if self.use_cookies:
            cookies = get_browser_cookies("reddit.com")
            if cookies:
                kwargs["cookies"] = cookies
                return kwargs
            logger.warning("Browser cookies not found for reddit.com, falling back to other auth")

        # Fall back to OAuth credentials if available
        if self.client_id and self.client_secret:
            import base64

            credentials = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
            kwargs["headers"]["Authorization"] = f"Basic {credentials}"

        return kwargs

    def _fetch_posts(self) -> list[dict]:
        url = f"https://www.reddit.com/r/{self.subreddit}/{self.sort}.json"
        params = {
            "limit": self.limit,
            "t": self.time_filter,
        }
        resp = requests.get(url, params=params, **self._request_kwargs())
        resp.raise_for_status()
        data = resp.json()
        return data["data"]["children"]

    _BLOCKED_DOMAINS = ("external-preview.redd.it", "preview.redd.it")

    def _is_valid_image_url(self, url: str) -> bool:
        """Check if a URL is a valid, high-resolution image."""
        if not url:
            return False
        for domain in self._BLOCKED_DOMAINS:
            if domain in url:
                return False
        return True

    def _extract_images(self, post: dict) -> list[str]:
        """Extract images from a Reddit post with full resolution priority.

        Priority order:
        1. Gallery posts: media_metadata (highest resolution)
        2. Image posts: url field (i.redd.it full resolution)
        3. Videos: secure_media.reddit_video.fallback_url
        4. Fallback: i.redd.it thumbnail only

        external-preview.redd.it URLs are rejected entirely — they return 403/404
        and cannot be converted to i.redd.it (different content hash per CDN).
        """
        images: list[str] = []

        # 1. Gallery posts - extract from media_metadata
        if post.get("gallery_data"):
            gallery_items = post.get("gallery_data", {}).get("items", [])
            media_metadata = post.get("media_metadata", {})
            for item in gallery_items:
                media_id = item.get("media_id")
                if media_id:
                    meta = media_metadata.get(media_id, {})
                    if meta:
                        # Get highest resolution from available resolutions
                        resolutions = meta.get("p", [])
                        if resolutions:
                            # Sort by width, get largest
                            largest = max(resolutions, key=lambda x: x.get("x", 0))
                            url = largest.get("u")
                            if url and url not in images and self._is_valid_image_url(url):
                                images.append(url)

        # 2. Direct image posts (i.redd.it URL)
        elif post.get("is_self") is False and post.get("url", "").startswith("https://i.redd.it"):
            url = post["url"]
            if url and url not in images and self._is_valid_image_url(url):
                images.append(url)

        # 3. Video posts
        elif post.get("secure_media"):
            secure_media = post.get("secure_media", {})
            if secure_media.get("reddit_video"):
                video_url = secure_media["reddit_video"].get("fallback_url")
                if video_url and video_url not in images and self._is_valid_image_url(video_url):
                    images.append(video_url)

        # 4. Fallback: i.redd.it thumbnail only (reject external-preview, they're broken)
        if not images:
            thumbnail = post.get("thumbnail", "")
            if thumbnail and thumbnail.startswith("https://i.redd.it/") and self._is_valid_image_url(thumbnail):
                images.append(thumbnail)

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

            # Link: always use Reddit permalink so users can read the discussion.
            # External URLs (corriere.it, etc.) lose the Reddit context.
            url = f"https://reddit.com{data['permalink']}"

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

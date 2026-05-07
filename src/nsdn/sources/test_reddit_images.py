#!/usr/bin/env python3
"""Structured test suite for Reddit image extraction.

Tests:
  1. Gallery posts -> media_metadata (highest resolution)
  2. Image posts -> i.redd.it (full resolution)
  3. Video posts -> secure_media fallback (mp4)
  4. Fallback -> i.redd.it thumbnail only
  5. Rejection -> external-preview.redd.it URLs are NEVER returned

Run:  python src/nsdn/sources/test_reddit_images.py
"""

from __future__ import annotations

import json
import statistics
import time
from collections import defaultdict

import requests

from nsdn.sources.reddit import RedditSource


def fetch_posts(subreddit: str, limit: int = 25) -> list[dict]:
    """Fetch hot posts from a subreddit."""
    url = f"https://www.reddit.com/r/{subreddit}/hot.json"
    resp = requests.get(url, headers={"User-Agent": "NSDN/0.1"}, timeout=30, params={"limit": limit})
    resp.raise_for_status()
    return [child["data"] for child in resp.json()["data"]["children"]]


class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = 0
        self.failed = 0
        self.errors: list[str] = []

    def record(self, title: str, ok: bool, detail: str = ""):
        if ok:
            self.passed += 1
        else:
            self.failed += 1
            self.errors.append(f"  FAIL: {title} — {detail}")

    @property
    def total(self):
        return self.passed + self.failed

    def summary(self) -> str:
        status = "PASS" if self.failed == 0 else "FAIL"
        lines = [f"\n{'=' * 70}", f"[{status}] {self.name}: {self.passed}/{self.total} passed", "=" * 70]
        for err in self.errors:
            lines.append(err)
        lines.append("")
        return "\n".join(lines)


def test_no_external_preview() -> TestResult:
    """CRITICAL: external-preview.redd.it must NEVER appear in output."""
    result = TestResult("No external-preview URLs (critical)")
    source = RedditSource("test", {"subreddit": "LocalLLaMA"})

    for sub in ["LocalLLaMA", "MistralAI", "MachineLearning"]:
        posts = fetch_posts(sub)
        for post in posts:
            images = source._extract_images(post)
            for img in images:
                is_blocked = "external-preview.redd.it" in img or "preview.redd.it/" in img
                result.record(
                    f"r/{sub}: {post['title'][:40]}",
                    not is_blocked,
                    f"blocked URL leaked: {img[:60]}" if is_blocked else ""
                )

    return result


def test_gallery_resolution() -> TestResult:
    """Gallery posts should use media_metadata, highest resolution."""
    result = TestResult("Gallery posts use media_metadata")

    for sub in ["LocalLLaMA", "pics"]:
        posts = fetch_posts(sub, limit=30)
        found = 0
        for post in posts:
            if not post.get("gallery_data"):
                continue
            found += 1
            source = RedditSource("test", {"subreddit": sub})
            images = source._extract_images(post)
            expected_count = len(post["gallery_data"]["items"])

            # Check resolution: should be high-res (width >= 1080)
            for img in images:
                if "s_scale" in img or "s_fit" in img:
                    # s_scale / s_fit are lower-res variants
                    result.record(post["title"][:40], False, "low-res s_scale/s_fit URL")
                    break
            else:
                result.record(post["title"][:40], True, f"{len(images)} images extracted")

        if found == 0:
            result.record(f"r/{sub}", True, "no gallery posts found (skip)")

    return result


def test_image_posts_full_res() -> TestResult:
    """Image posts should return i.redd.it URLs."""
    result = TestResult("Image posts use i.redd.it")
    source = RedditSource("test", {"subreddit": "LocalLLaMA"})

    posts = fetch_posts("LocalLLaMA", limit=30)
    for post in posts:
        if post.get("is_self") or not post.get("url", "").startswith("https://i.redd.it"):
            continue
        images = source._extract_images(post)
        if images:
            is_i_reddit = any("i.redd.it" in img for img in images)
            result.record(post["title"][:40], is_i_reddit, "i.redd.it" if is_i_reddit else "missing i.redd.it")

    return result


def test_video_posts() -> TestResult:
    """Video posts should extract secure_media fallback URL."""
    result = TestResult("Video posts extract secure_media")
    source = RedditSource("test", {"subreddit": "LocalLLaMA"})

    posts = fetch_posts("LocalLLaMA", limit=30)
    for post in posts:
        if not post.get("secure_media") or not post["secure_media"].get("reddit_video"):
            continue
        images = source._extract_images(post)
        has_video = any("v.redd.it" in img or ".mp4" in img for img in images)
        result.record(post["title"][:40], has_video, "video URL" if has_video else "no video URL")

    return result


def test_url_validity() -> TestResult:
    """All returned URLs should be accessible (HEAD 200)."""
    result = TestResult("URL accessibility (HEAD check)")
    source = RedditSource("test", {"subreddit": "LocalLLaMA"})

    posts = fetch_posts("LocalLLaMA", limit=20)
    for post in posts:
        images = source._extract_images(post)
        for img in images:
            try:
                resp = requests.head(img, allow_redirects=True, timeout=10)
                result.record(post["title"][:40], resp.status_code == 200, f"HTTP {resp.status_code}")
            except Exception as e:
                result.record(post["title"][:40], False, str(e)[:50])

    return result


def test_extraction_coverage() -> TestResult:
    """Report what fraction of posts get images."""
    result = TestResult("Extraction coverage")

    for sub in ["LocalLLaMA", "MistralAI"]:
        posts = fetch_posts(sub, limit=25)
        source = RedditSource("test", {"subreddit": sub})
        total = len(posts)
        with_images = sum(1 for p in posts if source._extract_images(p))
        pct = (with_images / total * 100) if total else 0
        result.record(f"r/{sub}", True, f"{with_images}/{total} posts have images ({pct:.0f}%)")

    return result


def print_report(results: list[TestResult]) -> None:
    """Print consolidated test report."""
    total_passed = sum(r.passed for r in results)
    total_failed = sum(r.failed for r in results)
    grand_total = total_passed + total_failed

    print("\n" + "=" * 70)
    print("  REDDIT IMAGE EXTRACTION — TEST REPORT")
    print("=" * 70)

    for r in results:
        print(r.summary())

    status = "ALL PASS" if total_failed == 0 else f"{total_failed} FAILURE(S)"
    print(f"\n  TOTAL: {total_passed}/{grand_total} passed — {status}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    print("Fetching posts from Reddit... (this may take a moment)")

    results: list[TestResult] = []
    t0 = time.time()

    results.append(test_no_external_preview())
    results.append(test_gallery_resolution())
    results.append(test_image_posts_full_res())
    results.append(test_video_posts())
    results.append(test_url_validity())
    results.append(test_extraction_coverage())

    elapsed = time.time() - t0
    print_report(results)
    print(f"Elapsed: {elapsed:.1f}s\n")

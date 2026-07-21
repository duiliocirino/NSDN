"""Browser cookie extraction for RSS feeds."""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def _find_firefox_cookie_path() -> str | None:
    """Find the Firefox cookies.sqlite file path.

    Checks standard locations and containerized Firefox profiles.
    Returns the path to cookies.sqlite or None if not found.
    """
    # Standard Firefox profile locations
    standard_paths = [
        Path.home() / ".mozilla" / "firefox",
        Path.home() / ".config" / "mozilla" / "firefox",
        Path.home() / ".var" / "app" / "org.mozilla.firefox" / ".mozilla" / "firefox",
    ]

    for base in standard_paths:
        if not base.is_dir():
            continue
        # Look for cookies.sqlite in any profile directory
        for profile_dir in base.iterdir():
            if profile_dir.is_dir():
                cookie_file = profile_dir / "cookies.sqlite"
                if cookie_file.is_file():
                    return str(cookie_file)

    # Check containerized Firefox (e.g., Flatpak/Snap) via /proc
    try:
        for pid_dir in Path("/proc").iterdir():
            if not pid_dir.is_dir() or not pid_dir.name.isdigit():
                continue
            cmdline = (pid_dir / "cmdline").read_text(errors="ignore")
            if "firefox" not in cmdline:
                continue
            # Found Firefox process, look for cookies in its root
            root_home = pid_dir / "root" / "home" / os.environ.get("USER", "") / ".config" / "mozilla" / "firefox"
            if root_home.is_dir():
                for profile_dir in root_home.iterdir():
                    cookie_file = profile_dir / "cookies.sqlite"
                    if cookie_file.is_file():
                        return str(cookie_file)
    except (PermissionError, OSError):
        pass

    return None


def get_browser_cookies(domain: str) -> dict[str, str]:
    """Extract cookies for a domain from the browser profile.

    Returns a dict of cookie name -> value for the given domain.
    Uses a temporary copy of cookies.sqlite to avoid locking issues
    when the browser is running.
    """
    cookie_path = _find_firefox_cookie_path()
    if not cookie_path:
        logger.debug("No Firefox cookie file found")
        return {}

    try:
        # Create a temporary copy to avoid locking issues
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            shutil.copy2(cookie_path, tmp_path)
            conn = sqlite3.connect(tmp_path)
            # Query cookies matching the domain (e.g., "reddit.com" matches ".reddit.com")
            query = """
                SELECT name, value, host FROM moz_cookies
                WHERE host LIKE ? OR host LIKE ?
            """
            cursor = conn.execute(
                query,
                (f"%{domain}%", f".{domain}"),
            )
            cookies: dict[str, str] = {}
            for name, value, _host in cursor.fetchall():
                cookies[name] = value
            conn.close()
            return cookies
        finally:
            os.unlink(tmp_path)
    except Exception as exc:
        logger.debug("Failed to read browser cookies: %s", exc)
        return {}

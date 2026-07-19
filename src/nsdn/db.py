"""SQLite database schema and queries."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Sequence

from nsdn.sources.base import FeedEntry

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    name TEXT NOT NULL,
    source_config TEXT,
    UNIQUE(source_type, name)
);

CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    guid TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    content TEXT,
    link TEXT,
    published_at TEXT,
    author TEXT,
    tags TEXT,
    images TEXT,
    score REAL,
    kept BOOLEAN DEFAULT 0,
    summarized BOOLEAN DEFAULT 0,
    processed_in_edition TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS editions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    slot TEXT NOT NULL,
    markdown_file TEXT,
    html_file TEXT,
    entry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, slot)
);

CREATE INDEX IF NOT EXISTS idx_entries_kept ON entries(kept);
CREATE INDEX IF NOT EXISTS idx_entries_processed ON entries(processed_in_edition);
CREATE INDEX IF NOT EXISTS idx_entries_score ON entries(score);
"""


class Database:
    def __init__(self, db_path: str = "data/feeds.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(SCHEMA_SQL)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Apply incremental migrations."""
        cols = [desc[1] for desc in self.conn.execute("PRAGMA table_info(entries)").fetchall()]
        if "summarized" not in cols:
            self.conn.execute("ALTER TABLE entries ADD COLUMN summarized BOOLEAN DEFAULT 0")
        if "designed_in_edition" in cols:
            # Remove — design is now a synthesize mode, not a separate output mode
            try:
                self.conn.execute("ALTER TABLE entries DROP COLUMN designed_in_edition")
            except sqlite3.OperationalError:
                pass  # Older SQLite doesn't support DROP COLUMN

    def upsert_source(self, source_type: str, name: str, source_config: dict | None = None) -> int:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO sources (source_type, name, source_config) VALUES (?, ?, ?)",
            (source_type, name, json.dumps(source_config) if source_config else None),
        )
        self.conn.commit()
        if cur.rowcount == 0:
            return self.get_source_id(source_type, name)
        return cur.lastrowid

    def get_source_id(self, source_type: str, name: str) -> int:
        cur = self.conn.execute(
            "SELECT id FROM sources WHERE source_type = ? AND name = ?",
            (source_type, name),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Source not found: {source_type}/{name}")
        return row[0]

    def insert_entries(self, entries: Sequence[FeedEntry], source_id: int) -> int:
        inserted = 0
        for entry in entries:
            try:
                self.conn.execute(
                    """INSERT INTO entries
                       (source_id, guid, title, summary, content, link, published_at, author, tags, images)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        source_id,
                        entry.guid,
                        entry.title,
                        entry.summary,
                        entry.content,
                        entry.link,
                        entry.published_at.isoformat() if entry.published_at else None,
                        entry.author,
                        json.dumps(entry.tags),
                        json.dumps(entry.images),
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                # Duplicate guid — skip
                pass
        self.conn.commit()
        return inserted

    def get_new_entries(self, limit: int | None = None) -> list[FeedEntry]:
        """Get unscored entries (score IS NULL)."""
        query = "SELECT * FROM entries WHERE score IS NULL ORDER BY created_at DESC"
        if limit:
            query += f" LIMIT {limit}"
        rows = self.conn.execute(query).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def get_kept_entries(self, processed: bool = False) -> list[FeedEntry]:
        """Get entries that passed the filter."""
        if processed:
            query = "SELECT * FROM entries WHERE kept = 1 AND processed_in_edition IS NOT NULL"
        else:
            query = "SELECT * FROM entries WHERE kept = 1 AND processed_in_edition IS NULL"
        rows = self.conn.execute(query).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def mark_processed(self, entry_guids: list[str], edition_date: str, edition_slot: str) -> None:
        placeholders = ",".join("?" for _ in entry_guids)
        self.conn.execute(
            f"UPDATE entries SET processed_in_edition = ? WHERE guid IN ({placeholders})",
            (edition_date,) + tuple(entry_guids),
        )
        self.conn.commit()

    def record_edition(
        self, date: str, slot: str, markdown_file: str, html_file: str, entry_count: int
    ) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO editions (date, slot, markdown_file, html_file, entry_count)
               VALUES (?, ?, ?, ?, ?)""",
            (date, slot, markdown_file, html_file, entry_count),
        )
        self.conn.commit()

    def cleanup_old_entries(self, keep_days: int) -> int:
        """Archive or delete entries older than keep_days."""
        cur = self.conn.execute(
            "DELETE FROM entries WHERE processed_in_edition IS NOT NULL AND created_at < datetime('now', ?)",
            (f"-{keep_days} days",),
        )
        self.conn.commit()
        return cur.rowcount

    def _row_to_entry(self, row: tuple) -> FeedEntry:
        from datetime import datetime

        cols = self._get_columns()
        d = dict(zip(cols, row))
        published_at = None
        if d.get("published_at"):
            try:
                published_at = datetime.fromisoformat(d["published_at"])
            except (ValueError, TypeError):
                pass
        score = d.get("score")
        return FeedEntry(
            source_type="",  # Not stored in entries table; resolve from source_id if needed
            source_name="",  # Not stored in entries table
            guid=d["guid"],
            title=d["title"],
            summary=d.get("summary"),
            content=d.get("content"),
            link=d.get("link"),
            published_at=published_at,
            author=d.get("author"),
            tags=json.loads(d["tags"]) if d.get("tags") else [],
            images=json.loads(d["images"]) if d.get("images") else [],
            score=float(score) if score is not None else 0.0,
        )

    def _get_columns(self) -> list[str]:
        return [desc[1] for desc in self.conn.execute("PRAGMA table_info(entries)").fetchall()]

    def close(self) -> None:
        self.conn.close()

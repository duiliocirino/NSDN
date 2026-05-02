"""DebugEmitter — structured JSON logging + artifact storage, gated by debug toggle."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class DebugEmitter:
    """No-op when debug is disabled. When enabled, writes structured trace + artifacts."""

    def __init__(self, enabled: bool, base_dir: Path, edition_slug: str = ""):
        self.enabled = enabled
        if enabled:
            self.artifacts_dir = base_dir / "debug" / edition_slug
            self.artifacts_dir.mkdir(parents=True, exist_ok=True)
            self._trace_path = self.artifacts_dir / "trace.jsonl"
            self._trace_path.write_text("", encoding="utf-8")  # create/clear
            self._trace_file = self._trace_path.open("a", encoding="utf-8")
        else:
            self.artifacts_dir = None  # type: ignore[assignment]
            self._trace_path = None  # type: ignore[assignment]
            self._trace_file = None  # type: ignore[assignment]

    def log_step(self, name: str, **metrics: Any) -> None:
        """Append a step to the structured trace."""
        if not self.enabled:
            return
        entry = {"step": name, "ts": time.time(), **metrics}
        self._trace_file.write(json.dumps(entry, default=_json_default) + "\n")  # type: ignore[union-attr]
        self._trace_file.flush()  # type: ignore[union-attr]

    def _ensure_parent(self, filename: str) -> Path:
        p = self.artifacts_dir / filename  # type: ignore[union-attr]
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def save_text(self, filename: str, content: str) -> None:
        """Save a text artifact (LLM output, spec, HTML, etc.)."""
        if not self.enabled:
            return
        self._ensure_parent(filename).write_text(content, encoding="utf-8")

    def save_bytes(self, filename: str, data: bytes) -> None:
        """Save a binary artifact (screenshot, PDF)."""
        if not self.enabled:
            return
        self._ensure_parent(filename).write_bytes(data)

    def save_json(self, filename: str, data: Any) -> None:
        """Save JSON data as an artifact."""
        if not self.enabled:
            return
        self._ensure_parent(filename).write_text(
            json.dumps(data, indent=2, default=_json_default), encoding="utf-8"
        )

    class StepTimer:
        """Context manager that times a step and logs it."""

        def __init__(self, emitter: "DebugEmitter", name: str, **extra: Any):
            self.emitter = emitter
            self.name = name
            self.extra = extra
            self.start = 0.0
            self.elapsed = 0.0

        def __enter__(self):
            self.start = time.time()
            return self

        def __exit__(self, *args):
            self.elapsed = time.time() - self.start
            self.emitter.log_step(self.name, duration_s=round(self.elapsed, 3), **self.extra)

    def timer(self, name: str, **extra: Any) -> StepTimer:
        """Return a context manager that logs duration on exit."""
        return self.StepTimer(self, name, **extra)

    def close(self) -> None:
        """Close the trace file handle."""
        if self.enabled and self._trace_file is not None:
            self._trace_file.close()
            self._trace_file = None

    def __enter__(self) -> "DebugEmitter":
        return self

    def __exit__(self, *args) -> None:
        self.close()


def _json_default(obj: Any) -> str:
    """JSON serializer fallback."""
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)

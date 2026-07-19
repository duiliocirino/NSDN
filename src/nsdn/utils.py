"""Shared utilities."""

from __future__ import annotations

from datetime import datetime


def get_slot() -> str:
    """Get time slot from current hour."""
    hour = datetime.now().hour
    if hour < 12:
        return "morning"
    elif hour < 17:
        return "afternoon"
    else:
        return "evening"

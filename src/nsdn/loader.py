"""Config loading utilities."""

from __future__ import annotations

from pathlib import Path

import yaml

from nsdn.config import AppConfig


DEFAULT_CONFIG_PATH = Path("config/nsdn.yaml")


def load_config(path: Path | str | None = None) -> AppConfig:
    """Load configuration from YAML file."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH

    if not config_path.exists():
        return AppConfig()

    with open(config_path, "r") as f:
        data = yaml.safe_load(f) or {}

    return AppConfig(**data)

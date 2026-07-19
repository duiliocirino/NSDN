"""Config loading utilities."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

from nsdn.config import AppConfig

logger = logging.getLogger(__name__)


DEFAULT_CONFIG_PATH = Path("config/nsdn.yaml")


def _resolve_env_vars(obj: Any) -> Any:
    """Recursively replace ${VAR_NAME} with os.environ values.

    If the environment variable is not set, the original ${VAR_NAME}
    is left unchanged so Pydantic validation can surface the issue.
    """

    if isinstance(obj, str):
        def _replace(match: re.Match) -> str:
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))

        return re.sub(r"\$\{([^}]+)\}", _replace, obj)
    elif isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve_env_vars(item) for item in obj]
    return obj


def load_config(path: Path | str | None = None) -> AppConfig:
    """Load configuration from YAML file.

    Resolves ${ENV_VAR} references in all string values before
    passing to Pydantic. Unresolved variables are left as-is.
    """
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH

    if not config_path.exists():
        return AppConfig()

    with open(config_path, "r") as f:
        data = yaml.safe_load(f) or {}

    data = _resolve_env_vars(data)
    return AppConfig(**data)

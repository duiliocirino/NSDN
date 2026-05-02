"""Newspaper agent registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from nsdn.config import AppConfig
from nsdn.db import Database
from nsdn.llm import LLMProvider
from nsdn.sources.base import FeedEntry

if TYPE_CHECKING:
    pass

NEWSPAPER_REGISTRY: dict[str, type] = {}


def register_newspaper(name: str, cls: type) -> None:
    NEWSPAPER_REGISTRY[name] = cls


def get_newspaper(name: str) -> type:
    if name not in NEWSPAPER_REGISTRY:
        raise ValueError(f"Unknown newspaper strategy: {name}. Available: {list(NEWSPAPER_REGISTRY.keys())}")
    return NEWSPAPER_REGISTRY[name]


def run_newspaper(
    config: AppConfig, db: Database, design_llm: LLMProvider, evaluate_llm: LLMProvider | None = None
) -> dict:
    """Dispatch to the configured newspaper strategy."""
    strategy_type = config.newspaper.strategy
    strategy_cls = get_newspaper(strategy_type)
    agent = strategy_cls(config, design_llm, evaluate_llm)
    return agent.run_design(db)


# Import implementations to register them
import nsdn.newspaper.component  # noqa: F401

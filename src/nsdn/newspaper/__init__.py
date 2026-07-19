"""Newspaper agent registry."""

from __future__ import annotations

from nsdn.config import AppConfig
from nsdn.db import Database
from nsdn.llm import LLMProvider
from nsdn.newspaper.base import NewspaperStrategy

NEWSPAPER_REGISTRY: dict[str, type[NewspaperStrategy]] = {}


def register_newspaper(name: str, cls: type[NewspaperStrategy]) -> None:
    NEWSPAPER_REGISTRY[name] = cls


def get_newspaper(name: str) -> type[NewspaperStrategy]:
    if name not in NEWSPAPER_REGISTRY:
        available = ", ".join(NEWSPAPER_REGISTRY.keys()) or "(none)"
        raise ValueError(f"Unknown newspaper strategy: {name}. Available: {available}")
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

"""Delivery target registry and orchestration."""

from __future__ import annotations

import logging
from pathlib import Path

from nsdn.config import AppConfig, DeliveryResult
from nsdn.delivery.base import DeliveryTarget
from nsdn.delivery.builder import build_content_info

logger = logging.getLogger(__name__)

DELIVERY_REGISTRY: dict[str, type[DeliveryTarget]] = {}


def register_delivery(target_type: str, target_class: type[DeliveryTarget]) -> None:
    """Register a delivery target class under the given type name."""
    DELIVERY_REGISTRY[target_type] = target_class


def get_delivery(target_type: str) -> type[DeliveryTarget]:
    """Get a registered delivery target class by type name."""
    if target_type not in DELIVERY_REGISTRY:
        available = ", ".join(DELIVERY_REGISTRY.keys()) or "(none)"
        raise ValueError(f"Unknown delivery type: {target_type}. Available: {available}")
    return DELIVERY_REGISTRY[target_type]


def run_delivery(config: AppConfig, edition_dir: Path) -> list[DeliveryResult]:
    """Execute delivery for all enabled targets.

    Builds content from the edition directory, then dispatches to each
    enabled target. Failures are logged and collected as failed results;
    they never raise.
    """
    content_info = build_content_info(edition_dir, config.delivery.content)

    results: list[DeliveryResult] = []
    for target_cfg in config.delivery.targets:
        if not target_cfg.enabled:
            logger.info("Skipping disabled delivery target: %s", target_cfg.label)
            continue

        target_cls = get_delivery(target_cfg.type)
        target = target_cls(target_cfg.label, target_cfg.config)
        try:
            result = target.deliver(content_info)
            results.append(result)
            if result.success:
                logger.info("Delivered to %s: %s", target_cfg.label, result.message)
            else:
                logger.warning("Delivery to %s failed: %s", target_cfg.label, result.message)
        except Exception as e:
            logger.error("Delivery failed for %s: %s", target_cfg.label, e)
            results.append(
                DeliveryResult(
                    target_type=target_cfg.type,
                    target_label=target_cfg.label,
                    success=False,
                    message=str(e),
                )
            )
    return results


# Auto-register implementations by importing them.
import nsdn.delivery.telegram  # noqa: F401  (registers "telegram")
import nsdn.delivery.email     # noqa: F401  (registers "email")

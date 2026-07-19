"""Telegram delivery target — sends edition PDFs via Bot API."""

from __future__ import annotations

import logging
from pathlib import Path

import requests

from nsdn.config import DeliveryResult
from nsdn.delivery.base import ContentInfo, DeliveryTarget

logger = logging.getLogger(__name__)


class TelegramDelivery(DeliveryTarget):
    """Deliver edition PDFs to a Telegram chat via Bot API sendDocument."""

    target_type = "telegram"

    def deliver(self, content_info: ContentInfo) -> DeliveryResult:
        bot_token = self.config.get("bot_token", "")
        chat_id = self.config.get("chat_id", "")
        caption_prefix = self.config.get("caption_prefix", "")

        if not bot_token or not chat_id:
            return DeliveryResult(
                target_type=self.target_type,
                target_label=self.label,
                success=False,
                message="bot_token and chat_id are required",
            )

        base_url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
        sent: list[str] = []
        errors: list[str] = []

        # Build caption text
        caption_text = content_info.caption
        if caption_prefix:
            caption_text = f"{caption_prefix}\n{caption_text}"

        # Send desktop PDF first (with caption)
        if content_info.pdf_path and content_info.pdf_path.exists():
            result = _send_document(
                base_url, chat_id, content_info.pdf_path, caption_text
            )
            if result["ok"]:
                sent.append("desktop PDF")
            else:
                errors.append(f"desktop PDF: {result.get('description', 'unknown error')}")

        # Send mobile PDF (without caption to avoid duplicate text)
        if content_info.mobile_pdf_path and content_info.mobile_pdf_path.exists():
            result = _send_document(
                base_url, chat_id, content_info.mobile_pdf_path, ""
            )
            if result["ok"]:
                sent.append("mobile PDF")
            else:
                errors.append(f"mobile PDF: {result.get('description', 'unknown error')}")

        if sent and not errors:
            return DeliveryResult(
                target_type=self.target_type,
                target_label=self.label,
                success=True,
                message=f"Sent: {', '.join(sent)}",
            )
        elif sent:
            return DeliveryResult(
                target_type=self.target_type,
                target_label=self.label,
                success=True,
                message=f"Sent: {', '.join(sent)}. Errors: {', '.join(errors)}",
            )
        else:
            return DeliveryResult(
                target_type=self.target_type,
                target_label=self.label,
                success=False,
                message=f"All sends failed: {', '.join(errors)}",
            )


def _send_document(
    base_url: str, chat_id: str, pdf_path: Path, caption: str
) -> dict:
    """Send a single PDF as a document to a Telegram chat."""
    timeout = 60  # PDFs can be large
    with open(pdf_path, "rb") as f:
        files = {"document": (pdf_path.name, f, "application/pdf")}
        data = {"chat_id": chat_id}
        if caption:
            # Telegram captions are limited to 1024 characters
            data["caption"] = caption[:1024]

        logger.info("Sending %s to Telegram chat %s", pdf_path.name, chat_id)
        resp = requests.post(base_url, data=data, files=files, timeout=timeout)
        result = resp.json()

        if not result.get("ok"):
            logger.error(
                "Telegram API error: %s (HTTP %d)",
                result.get("description", "unknown"),
                resp.status_code,
            )
        return result


# Auto-register on import
from nsdn.delivery import register_delivery  # noqa: E402

register_delivery("telegram", TelegramDelivery)

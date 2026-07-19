"""Email delivery target — sends edition PDFs via SMTP."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from nsdn.config import DeliveryResult
from nsdn.delivery.base import ContentInfo, DeliveryTarget

logger = logging.getLogger(__name__)


class EmailDelivery(DeliveryTarget):
    """Deliver edition PDFs via SMTP email."""

    target_type = "email"

    def deliver(self, content_info: ContentInfo) -> DeliveryResult:
        method = self.config.get("method", "smtp").lower()

        if method == "smtp":
            return self._deliver_smtp(content_info)
        else:
            return DeliveryResult(
                target_type=self.target_type,
                target_label=self.label,
                success=False,
                message=f"Unsupported method: {method}",
            )

    def _deliver_smtp(self, content_info: ContentInfo) -> DeliveryResult:
        host = self.config.get("smtp_host", "")
        port = int(self.config.get("smtp_port", 587))
        user = self.config.get("smtp_user", "")
        password = self.config.get("smtp_password", "")
        from_addr = self.config.get("from", "")
        to_addrs = self.config.get("to", [])

        if not all([host, user, password, from_addr, to_addrs]):
            return DeliveryResult(
                target_type=self.target_type,
                target_label=self.label,
                success=False,
                message="smtp_host, smtp_user, smtp_password, from, and to are required",
            )

        # Build subject from template or default
        subject_template = self.config.get(
            "subject_template", "NSDN — {date} ({slot})"
        )
        try:
            subject = subject_template.format(
                date=content_info.date,
                slot=content_info.slot,
                topics=", ".join(content_info.topics),
                entry_count=content_info.entry_count,
            )
        except KeyError:
            subject = f"NSDN — {content_info.date}"

        msg = MIMEMultipart()
        msg["From"] = from_addr
        msg["To"] = ", ".join(to_addrs)
        msg["Subject"] = subject

        # Body
        msg.attach(MIMEText(content_info.caption or "No caption", "plain"))

        # Attach desktop PDF
        if content_info.pdf_path and content_info.pdf_path.exists():
            attachment = MIMEApplication(
                content_info.pdf_path.read_bytes(),
                Name=f"edition-{content_info.date}-{content_info.slot}.pdf",
            )
            attachment["Content-Disposition"] = (
                f"attachment; filename=\"edition-{content_info.date}-{content_info.slot}.pdf\""
            )
            msg.attach(attachment)

        # Attach mobile PDF
        if content_info.mobile_pdf_path and content_info.mobile_pdf_path.exists():
            attachment = MIMEApplication(
                content_info.mobile_pdf_path.read_bytes(),
                Name=f"edition-{content_info.date}-{content_info.slot}-mobile.pdf",
            )
            attachment["Content-Disposition"] = (
                f"attachment; filename=\"edition-{content_info.date}-{content_info.slot}-mobile.pdf\""
            )
            msg.attach(attachment)

        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(user, password)
                server.sendmail(from_addr, to_addrs, msg.as_string())

            return DeliveryResult(
                target_type=self.target_type,
                target_label=self.label,
                success=True,
                message=f"Sent to {', '.join(to_addrs)}",
            )
        except Exception as e:
            logger.error("SMTP delivery failed: %s", e)
            return DeliveryResult(
                target_type=self.target_type,
                target_label=self.label,
                success=False,
                message=str(e),
            )


# Auto-register on import
from nsdn.delivery import register_delivery  # noqa: E402

register_delivery("email", EmailDelivery)

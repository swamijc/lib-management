"""
Notification Service — Email channel (aiosmtplib).

Sends HTML email via SMTP with TLS. Credentials come from settings
or from runtime override (when configured via UI/DB).
"""
from __future__ import annotations

import structlog
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ..config import settings

logger = structlog.get_logger(__name__)


async def send_email(
    recipients: list[str],
    subject: str,
    html_body: str,
    smtp_override: "dict | None" = None,
) -> None:
    """
    Send HTML email via aiosmtplib.
    Uses smtp_override credentials if provided (from DB config), else falls
    back to environment-variable settings.

    smtp_override keys: host, port, username, password, from_address, use_tls
    """
    import aiosmtplib  # deferred import so missing pkg doesn't break startup

    ov = smtp_override or {}
    host     = ov.get("host")     or settings.smtp_host
    port     = int(ov.get("port") or settings.smtp_port)
    username = ov.get("username") or settings.smtp_username
    password = ov.get("password") or settings.smtp_password
    from_addr= ov.get("from_address") or settings.smtp_from_address
    use_tls  = ov.get("use_tls", settings.smtp_use_tls)
    if isinstance(use_tls, str):
        use_tls = use_tls.lower() not in ("0","false","no")

    if not username or not password or not from_addr:
        raise RuntimeError(
            "Email not configured — set SMTP credentials in ⚙️ Settings → 🔔 Notifications Config"
        )

    resolved = recipients or settings.default_recipients_list
    if not resolved:
        raise RuntimeError(
            "No recipients — add email addresses in ⚙️ Settings → 🔔 Notifications Config"
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = from_addr
    msg["To"]      = ", ".join(resolved)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    logger.info("email_send_start", recipients=resolved, subject=subject, host=host)
    await aiosmtplib.send(
        msg,
        hostname=host,
        port=port,
        username=username,
        password=password,
        start_tls=use_tls,
    )
    logger.info("email_send_success", recipients=resolved)

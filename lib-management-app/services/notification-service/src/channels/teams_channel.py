"""
Notification Service — Microsoft Teams channel (httpx POST to Incoming Webhook).

Posts an Adaptive Card payload to the configured Teams webhook URL.
"""
from __future__ import annotations

import httpx
import structlog

from ..config import settings

logger = structlog.get_logger(__name__)


async def send_teams(card_payload: dict, webhook_url: str | None = None) -> None:
    """
    POST an Adaptive Card payload to the Teams Incoming Webhook URL.
    Uses webhook_url override when provided (from DB config), else settings.

    Raises:
        RuntimeError — if Teams is not configured
        httpx.HTTPStatusError — on non-2xx response
    """
    url = webhook_url or settings.teams_webhook_url
    if not url:
        raise RuntimeError(
            "Teams not configured — add the webhook URL in ⚙️ Settings → 🔔 Notifications Config"
        )

    logger.info("teams_send_start", webhook=url[:60] + "…")
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            url,
            json=card_payload,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
    logger.info("teams_send_success")

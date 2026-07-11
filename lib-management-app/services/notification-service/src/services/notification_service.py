"""
Notification Service — orchestrator.

Responsibilities:
  1. Build template context from the library list
  2. Check dedup hash (B2 gap) — skip if same payload sent within dedup_min_hours
  3. Dispatch to email and/or Teams channels
  4. Return per-channel results
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone, timedelta

import structlog

from ..channels.email_channel import send_email
from ..channels.teams_channel import send_teams
from ..config import settings
from ..models.schemas import (
    ChannelResult,
    LibrarySummaryItem,
    NotificationChannel,
    NotificationStatus,
    NotifyRequest,
    NotifyResult,
)
from ..templates.notification_templates import render_email_html, render_teams_card

logger = structlog.get_logger(__name__)

# In-memory dedup store: hash → last_sent datetime (resets on restart)
_sent_hashes: dict[str, datetime] = {}


class NotificationService:

    # ── Deduplication (B2 gap) ───────────────────────────────────────────────

    @staticmethod
    def _compute_hash(libraries: list[LibrarySummaryItem]) -> str:
        """Stable hash of the library payload for dedup comparison."""
        payload = sorted(
            [{"id": lib.library_id, "pkg": lib.package, "rec": lib.upgrade_recommended}
             for lib in libraries],
            key=lambda x: x["id"],
        )
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]

    @staticmethod
    def _is_duplicate(payload_hash: str) -> bool:
        last = _sent_hashes.get(payload_hash)
        if last is None:
            return False
        return (datetime.now(timezone.utc) - last) < timedelta(hours=settings.dedup_min_hours)

    @staticmethod
    def _record_hash(payload_hash: str) -> None:
        _sent_hashes[payload_hash] = datetime.now(timezone.utc)

    # ── Template context builder ──────────────────────────────────────────────

    @staticmethod
    def _build_context(libraries: list[LibrarySummaryItem]) -> dict:
        mandatory = [l for l in libraries if l.update_needed == "Mandatory"]
        deprecated = [l for l in libraries if (l.library_status or "").lower() == "deprecated"]
        recommended = [l for l in libraries if l.update_needed == "Recommended"]
        sufficient = [l for l in libraries
                      if l.upgrade_recommended == "Sufficient"
                      and (l.library_status or "").lower() != "deprecated"]
        critical = [l for l in libraries if l.alert_priority == "Critical"]

        action_lines = " | ".join(
            f"{l.package} ({l.update_needed})" for l in (mandatory + deprecated)[:5]
        )

        return {
            "libraries": libraries,
            "mandatory_items": mandatory,
            "deprecated_items": deprecated,
            "recommended_items": recommended,
            "sufficient_items": sufficient,
            "critical_items": critical,
            "action_lines": action_lines,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        }

    # ── Public dispatch methods ───────────────────────────────────────────────

    async def notify_email(self, req: NotifyRequest) -> NotifyResult:
        payload_hash = self._compute_hash(req.libraries)
        if not req.force_send and self._is_duplicate(payload_hash):
            logger.info("email_dedup_skip", hash=payload_hash)
            return NotifyResult(
                channels_attempted=["email"],
                results=[ChannelResult(
                    channel=NotificationChannel.EMAIL,
                    status=NotificationStatus.SKIPPED,
                    message="Duplicate payload — already sent within dedup window",
                )],
                dedup_hash=payload_hash,
                skipped_by_dedup=True,
            )

        context = self._build_context(req.libraries)
        html = render_email_html(context)

        # Build SMTP override dict from request (when credentials set via UI/DB)
        smtp_ov = None
        if req.smtp_override and req.smtp_override.username:
            smtp_ov = req.smtp_override.model_dump()

        try:
            await send_email(
                recipients=req.recipients or settings.default_recipients_list,
                subject=req.subject,
                html_body=html,
                smtp_override=smtp_ov,
            )
            self._record_hash(payload_hash)
            result = ChannelResult(
                channel=NotificationChannel.EMAIL,
                status=NotificationStatus.SENT,
                message="Email sent successfully",
            )
        except Exception as exc:
            logger.error("email_send_failed", error=str(exc))
            result = ChannelResult(
                channel=NotificationChannel.EMAIL,
                status=NotificationStatus.FAILED,
                message=str(exc),
            )

        return NotifyResult(
            channels_attempted=["email"],
            results=[result],
            dedup_hash=payload_hash,
        )

    async def notify_teams(self, req: NotifyRequest) -> NotifyResult:
        payload_hash = self._compute_hash(req.libraries)
        if not req.force_send and self._is_duplicate(payload_hash):
            logger.info("teams_dedup_skip", hash=payload_hash)
            return NotifyResult(
                channels_attempted=["teams"],
                results=[ChannelResult(
                    channel=NotificationChannel.TEAMS,
                    status=NotificationStatus.SKIPPED,
                    message="Duplicate payload — already sent within dedup window",
                )],
                dedup_hash=payload_hash,
                skipped_by_dedup=True,
            )

        context = self._build_context(req.libraries)
        try:
            card = render_teams_card(context)
            webhook_ov = req.teams_webhook_override or None
            await send_teams(card, webhook_url=webhook_ov)
            self._record_hash(payload_hash)
            result = ChannelResult(
                channel=NotificationChannel.TEAMS,
                status=NotificationStatus.SENT,
                message="Teams message sent successfully",
            )
        except Exception as exc:
            logger.error("teams_send_failed", error=str(exc))
            result = ChannelResult(
                channel=NotificationChannel.TEAMS,
                status=NotificationStatus.FAILED,
                message=str(exc),
            )

        return NotifyResult(
            channels_attempted=["teams"],
            results=[result],
            dedup_hash=payload_hash,
        )

    async def notify_both(self, req: NotifyRequest) -> NotifyResult:
        payload_hash = self._compute_hash(req.libraries)
        if not req.force_send and self._is_duplicate(payload_hash):
            return NotifyResult(
                channels_attempted=["email", "teams"],
                results=[
                    ChannelResult(channel=NotificationChannel.EMAIL,
                                  status=NotificationStatus.SKIPPED,
                                  message="Duplicate payload"),
                    ChannelResult(channel=NotificationChannel.TEAMS,
                                  status=NotificationStatus.SKIPPED,
                                  message="Duplicate payload"),
                ],
                dedup_hash=payload_hash,
                skipped_by_dedup=True,
            )

        results: list[ChannelResult] = []
        context = self._build_context(req.libraries)
        html = render_email_html(context)

        # Email
        try:
            await send_email(
                recipients=req.recipients or settings.default_recipients_list,
                subject=req.subject,
                html_body=html,
            )
            results.append(ChannelResult(channel=NotificationChannel.EMAIL,
                                         status=NotificationStatus.SENT,
                                         message="Email sent successfully"))
        except Exception as exc:
            results.append(ChannelResult(channel=NotificationChannel.EMAIL,
                                         status=NotificationStatus.FAILED,
                                         message=str(exc)))

        # Teams
        try:
            card = render_teams_card(context)
            await send_teams(card)
            results.append(ChannelResult(channel=NotificationChannel.TEAMS,
                                         status=NotificationStatus.SENT,
                                         message="Teams message sent successfully"))
        except Exception as exc:
            results.append(ChannelResult(channel=NotificationChannel.TEAMS,
                                         status=NotificationStatus.FAILED,
                                         message=str(exc)))

        any_sent = any(r.status == NotificationStatus.SENT for r in results)
        if any_sent:
            self._record_hash(payload_hash)

        return NotifyResult(
            channels_attempted=["email", "teams"],
            results=results,
            dedup_hash=payload_hash,
        )

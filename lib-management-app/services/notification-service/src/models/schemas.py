"""Notification Service — Pydantic v2 DTOs."""
from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class NotificationChannel(str, Enum):
    EMAIL = "email"
    TEAMS = "teams"
    BOTH = "both"


class NotificationStatus(str, Enum):
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"   # dedup: same hash sent recently (B2)


# ── Library summary item (input) ──────────────────────────────────────────────

class LibrarySummaryItem(BaseModel):
    library_id: int
    package: str
    platform: str
    current_version: str
    latest_version: str
    update_needed: str | None = None
    library_status: str | None = None
    upgrade_recommended: str | None = None   # Yes / No / Sufficient
    recommendation_summary: str | None = None
    alert_priority: str | None = None        # Critical / High / Normal
    deadline_date: str | None = None
    deadline_notes: str | None = None


# ── Notification requests ─────────────────────────────────────────────────────

class SmtpOverride(BaseModel):
    """Runtime SMTP credentials — used when env vars are not configured."""
    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    from_address: str = ""
    use_tls: bool = True


class NotifyRequest(BaseModel):
    """Payload for all /notify/* endpoints."""
    libraries: list[LibrarySummaryItem] = Field(..., min_length=1)
    recipients: list[str] = Field(
        default=[],
        description="Email recipients. Falls back to SMTP defaults if empty.",
    )
    subject: str = Field(
        default="SDK Management — Upgrade Report",
    )
    force_send: bool = False
    # Optional credential overrides — used when channels configured via UI/DB
    smtp_override: SmtpOverride | None = None
    teams_webhook_override: str | None = None


# ── Notification results ──────────────────────────────────────────────────────

class ChannelResult(BaseModel):
    channel: NotificationChannel
    status: NotificationStatus
    message: str
    sent_at: datetime = Field(default_factory=_utcnow)

    model_config = {"use_enum_values": True}


class NotifyResult(BaseModel):
    channels_attempted: list[str]
    results: list[ChannelResult]
    dedup_hash: str
    skipped_by_dedup: bool = False
    generated_at: datetime = Field(default_factory=_utcnow)

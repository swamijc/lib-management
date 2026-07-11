"""Notification Service — configuration."""
from __future__ import annotations
from pydantic import Field
from shared.config.base_settings import ServiceSettings


class Settings(ServiceSettings):
    service_name: str = "notification-service"
    service_version: str = "1.0.0"

    # ── SMTP (email) ─────────────────────────────────────────────────────────
    smtp_host: str = Field(default="smtp.office365.com")
    smtp_port: int = Field(default=587)
    smtp_username: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_from_address: str = Field(default="library-mgmt@example.com")
    smtp_use_tls: bool = True
    # Comma-separated default recipients (overridable per request)
    default_email_recipients: str = Field(default="")

    # ── Microsoft Teams ───────────────────────────────────────────────────────
    teams_webhook_url: str = Field(
        default="",
        description="Teams Incoming Webhook URL (leave empty to disable Teams)",
    )

    # ── Deduplication (B2 gap) ───────────────────────────────────────────────
    # Min hours between sending the same notification payload hash
    dedup_min_hours: int = 24

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_username and self.smtp_password and self.smtp_from_address)

    @property
    def teams_enabled(self) -> bool:
        return bool(self.teams_webhook_url)

    @property
    def default_recipients_list(self) -> list[str]:
        return [r.strip() for r in self.default_email_recipients.split(",") if r.strip()]


settings = Settings()

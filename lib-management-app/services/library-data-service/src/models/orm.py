"""
SQLAlchemy ORM models — maps existing DB tables.
These are domain objects; never exposed directly over the API (use schemas.py).
"""
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import (
    CheckConstraint, Float, ForeignKey, Index, Integer,
    Text, UniqueConstraint, event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Library ───────────────────────────────────────────────────────────────────
class Library(Base):
    __tablename__ = "libraries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sl_no: Mapped[int | None] = mapped_column(Integer)
    package: Mapped[str] = mapped_column(Text, nullable=False)
    sdk_name: Mapped[str | None] = mapped_column(Text)
    platform: Mapped[str] = mapped_column(
        Text, nullable=False,
        # existing check constraint in DB — mirrors here for clarity
    )
    current_version: Mapped[str | None] = mapped_column(Text)
    latest_version: Mapped[str | None] = mapped_column(Text)
    update_needed: Mapped[str] = mapped_column(Text, default="None")
    priority: Mapped[str | None] = mapped_column(Text)
    repo_url: Mapped[str | None] = mapped_column(Text)
    registry: Mapped[str | None] = mapped_column(Text)
    comments: Mapped[str | None] = mapped_column(Text)
    deprecation_notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="Unknown")
    source_date: Mapped[str | None] = mapped_column(Text)
    last_checked_date: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, default=_now)
    updated_at: Mapped[str] = mapped_column(Text, default=_now, onupdate=_now)

    # New columns added in migration 001
    alert_priority: Mapped[str] = mapped_column(Text, default="Normal")
    deadline_date: Mapped[str | None] = mapped_column(Text)
    deadline_notes: Mapped[str | None] = mapped_column(Text)
    ecosystem: Mapped[str] = mapped_column(Text, default="mobile")
    framework_language: Mapped[str | None] = mapped_column(Text)

    # Relationships
    version_history: Mapped[list["VersionHistory"]] = relationship(
        back_populates="library", cascade="all, delete-orphan"
    )
    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="library", cascade="all, delete-orphan"
    )
    external_sources: Mapped[list["LibraryExternalSource"]] = relationship(
        back_populates="library", cascade="all, delete-orphan"
    )
    update_logs: Mapped[list["LibraryUpdateLog"]] = relationship(
        back_populates="library", cascade="all, delete-orphan"
    )
    upgrade_lifecycle: Mapped[list["UpgradeLifecycle"]] = relationship(
        back_populates="library", cascade="all, delete-orphan"
    )
    scrape_caches: Mapped[list["ScrapeCache"]] = relationship(
        back_populates="library", cascade="all, delete-orphan"
    )
    cve_caches: Mapped[list["CveCache"]] = relationship(
        "CveCache", foreign_keys="[CveCache.library_id]", cascade="all, delete-orphan"
    )
    ownerships: Mapped[list["LibraryOwnership"]] = relationship(
        "LibraryOwnership", foreign_keys="[LibraryOwnership.library_id]", cascade="all, delete-orphan"
    )
    versions: Mapped[list["LibraryVersion"]] = relationship(
        "LibraryVersion", foreign_keys="[LibraryVersion.library_id]",
        cascade="all, delete-orphan", order_by="LibraryVersion.release_date.desc()"
    )

    __table_args__ = (
        Index("idx_lib_platform", "platform"),
        Index("idx_lib_status", "status"),
        Index("idx_lib_update", "update_needed"),
        Index("idx_lib_package", "package"),
    )


# ── Version History ───────────────────────────────────────────────────────────
class VersionHistory(Base):
    __tablename__ = "version_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    library_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("libraries.id"), nullable=False
    )
    version_number: Mapped[str] = mapped_column(Text, nullable=False)
    record_type: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_at: Mapped[str] = mapped_column(Text, default=_now)

    library: Mapped["Library"] = relationship(back_populates="version_history")

    __table_args__ = (
        CheckConstraint(
            "record_type IN ('current','latest','previous')",
            name="ck_version_history_type",
        ),
        Index("idx_ver_lib", "library_id"),
    )


# ── Recommendation ────────────────────────────────────────────────────────────
class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    library_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("libraries.id"), nullable=False
    )
    priority: Mapped[str | None] = mapped_column(Text)
    upgrade_recommended: Mapped[str | None] = mapped_column(Text)
    recommendation_summary: Mapped[str | None] = mapped_column(Text)
    upgrade_pros: Mapped[str | None] = mapped_column(Text)  # JSON array
    upgrade_cons: Mapped[str | None] = mapped_column(Text)  # JSON array
    no_upgrade_pros: Mapped[str | None] = mapped_column(Text)  # JSON array
    no_upgrade_cons: Mapped[str | None] = mapped_column(Text)  # JSON array
    generated_at: Mapped[str] = mapped_column(Text, default=_now)

    library: Mapped["Library"] = relationship(back_populates="recommendations")

    __table_args__ = (
        CheckConstraint(
            "priority IS NULL OR priority IN ('critical','high','moderate','low','none','manual_review')",
            name="ck_rec_priority",
        ),
        CheckConstraint(
            "upgrade_recommended IN ('Yes','No','Sufficient')",
            name="ck_rec_upgrade",
        ),
        Index("idx_rec_lib", "library_id"),
    )


# ── Library External Source ───────────────────────────────────────────────────
class LibraryExternalSource(Base):
    __tablename__ = "library_external_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    library_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("libraries.id"), nullable=False
    )
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, default="custom")
    added_by: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(Text, default=_now)

    library: Mapped["Library"] = relationship(back_populates="external_sources")


# ── Library Update Log (append-only — enforced by DB triggers) ────────────────
class LibraryUpdateLog(Base):
    __tablename__ = "library_update_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    library_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("libraries.id"), nullable=False
    )
    updated_by: Mapped[str] = mapped_column(Text, nullable=False)
    update_type: Mapped[str] = mapped_column(Text, nullable=False)
    field_changed: Mapped[str] = mapped_column(Text, nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(Text, default=_now)

    library: Mapped["Library"] = relationship(back_populates="update_logs")

    __table_args__ = (Index("idx_upd_log_library", "library_id"),)


# ── Upgrade Lifecycle (B1) ────────────────────────────────────────────────────
class UpgradeLifecycle(Base):
    __tablename__ = "upgrade_lifecycle"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    library_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("libraries.id"), nullable=False
    )
    recommendation_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("recommendations.id")
    )
    status: Mapped[str] = mapped_column(Text, default="Pending")
    target_version: Mapped[str | None] = mapped_column(Text)
    target_sprint: Mapped[str | None] = mapped_column(Text)
    target_date: Mapped[str | None] = mapped_column(Text)
    completed_version: Mapped[str | None] = mapped_column(Text)
    skip_reason: Mapped[str | None] = mapped_column(Text)
    actioned_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, default=_now)
    updated_at: Mapped[str] = mapped_column(Text, default=_now, onupdate=_now)

    library: Mapped["Library"] = relationship(back_populates="upgrade_lifecycle")

    __table_args__ = (
        CheckConstraint(
            "status IN ('Pending','Acknowledged','Scheduled','In Progress','Completed','Skipped')",
            name="ck_lifecycle_status",
        ),
        Index("idx_lifecycle_library", "library_id"),
    )


# ── Scrape Cache (T1) ─────────────────────────────────────────────────────────
class ScrapeCache(Base):
    __tablename__ = "scrape_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    library_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("libraries.id"), nullable=False
    )
    registry_key: Mapped[str] = mapped_column(Text, nullable=False)
    scraped_version: Mapped[str] = mapped_column(Text, nullable=False)
    release_notes: Mapped[str | None] = mapped_column(Text)
    raw_response: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[str] = mapped_column(Text, nullable=False)
    scraped_at: Mapped[str] = mapped_column(Text, default=_now)

    library: Mapped["Library"] = relationship(back_populates="scrape_caches")

    __table_args__ = (
        UniqueConstraint("library_id", "registry_key", name="uq_scrape_cache"),
        Index("idx_scrape_cache_expiry", "expires_at"),
    )


# ── Pipeline Runs ─────────────────────────────────────────────────────────────
class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    triggered_by: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="running")
    libraries_processed: Mapped[int] = mapped_column(Integer, default=0)
    libraries_updated: Mapped[int] = mapped_column(Integer, default=0)
    errors_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[str] = mapped_column(Text, default=_now)
    finished_at: Mapped[str | None] = mapped_column(Text)
    steps_json: Mapped[str | None] = mapped_column(Text)  # JSON-serialized list[StepResult]

    details: Mapped[list["PipelineRunDetail"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('running','completed','partial','failed')",
            name="ck_pipeline_status",
        ),
        Index("idx_pipeline_status", "status"),
    )


# ── Pipeline Run Details ──────────────────────────────────────────────────────
class PipelineRunDetail(Base):
    __tablename__ = "pipeline_run_details"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        Text, ForeignKey("pipeline_runs.run_id"), nullable=False
    )
    library_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("libraries.id")
    )
    step: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    recorded_at: Mapped[str] = mapped_column(Text, default=_now)

    run: Mapped["PipelineRun"] = relationship(back_populates="details")


# ── Notifications ─────────────────────────────────────────────────────────────
class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    library_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("libraries.id")
    )
    notification_type: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="Pending")
    sent_at: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, default=_now)


# ── Notification Sent Log (B2 dedup) ──────────────────────────────────────────
class NotificationSentLog(Base):
    __tablename__ = "notification_sent_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    library_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("libraries.id"), nullable=False
    )
    notification_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("notifications.id")
    )
    latest_version_at_send: Mapped[str | None] = mapped_column(Text)
    update_needed_at_send: Mapped[str | None] = mapped_column(Text)
    status_at_send: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[str] = mapped_column(Text, default=_now)

    __table_args__ = (Index("idx_notif_sent_library", "library_id"),)


# ── LLM Config (admin-managed) ────────────────────────────────────────────────
class LlmConfig(Base):
    __tablename__ = "llm_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(Text, default="openai", nullable=False)
    model_name: Mapped[str] = mapped_column(Text, default="gpt-4o", nullable=False)
    api_base_url: Mapped[str | None] = mapped_column(Text)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text)
    api_version: Mapped[str | None] = mapped_column(Text)
    temperature: Mapped[float] = mapped_column(Float, default=0.3, nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, default=1024, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    enabled: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(Text, default=_now, onupdate=_now)

    __table_args__ = (
        CheckConstraint(
            "provider IN ('openai','azure_openai','anthropic','ollama')",
            name="ck_llm_provider",
        ),
    )


# ── LLM Prompt Templates ───────────────────────────────────────────────────────
class LlmPromptTemplate(Base):
    __tablename__ = "llm_prompt_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prompt_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    template_text: Mapped[str] = mapped_column(Text, nullable=False)
    variables_hint: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(Text, default=_now, onupdate=_now)


# ── App Settings (key/value) ───────────────────────────────────────────────────
class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_sensitive: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(Text, default=_now, onupdate=_now)


# ── LLM Usage Log (T5) ───────────────────────────────────────────────────────
class LLMUsageLog(Base):
    __tablename__ = "llm_usage_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("pipeline_runs.run_id")
    )
    library_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("libraries.id")
    )
    prompt_key: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    logged_at: Mapped[str] = mapped_column(Text, default=_now)

    __table_args__ = (Index("idx_llm_usage_run", "run_id"),)


# ── Application Teams ─────────────────────────────────────────────────────────
class ApplicationTeam(Base):
    __tablename__ = "application_teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    team_email: Mapped[str | None] = mapped_column(Text)
    teams_channel: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, default=_now)

    ownerships: Mapped[list["LibraryOwnership"]] = relationship(
        back_populates="team", cascade="all, delete-orphan"
    )


# ── Library Ownership ─────────────────────────────────────────────────────────
class LibraryOwnership(Base):
    __tablename__ = "library_ownership"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    library_id: Mapped[int] = mapped_column(Integer, ForeignKey("libraries.id"), nullable=False)
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("application_teams.id"), nullable=False)
    is_primary: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    assigned_by: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_at: Mapped[str] = mapped_column(Text, default=_now)

    team: Mapped["ApplicationTeam"] = relationship(back_populates="ownerships")

    __table_args__ = (
        UniqueConstraint("library_id", "team_id", name="uq_lib_ownership"),
    )


# ── CVE Cache (OSV.dev results) ───────────────────────────────────────────────
class CveCache(Base):
    __tablename__ = "cve_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    library_id: Mapped[int] = mapped_column(Integer, ForeignKey("libraries.id"), nullable=False)
    ecosystem: Mapped[str] = mapped_column(Text, nullable=False)
    version_checked: Mapped[str] = mapped_column(Text, nullable=False)
    vuln_count: Mapped[int] = mapped_column(Integer, default=0)
    vulns_json: Mapped[str | None] = mapped_column(Text)   # JSON array of vuln summaries
    scanned_at: Mapped[str] = mapped_column(Text, default=_now)

    __table_args__ = (
        UniqueConstraint("library_id", "version_checked", name="uq_cve_cache"),
        Index("idx_cve_library", "library_id"),
    )


# ── Library Versions (all historical versions + release notes) ────────────────
class LibraryVersion(Base):
    __tablename__ = "library_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    library_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("libraries.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(Text, nullable=False)
    release_date: Mapped[str | None] = mapped_column(Text)   # YYYY-MM-DD
    release_notes: Mapped[str | None] = mapped_column(Text)  # markdown / plain text
    maven_url: Mapped[str | None] = mapped_column(Text)
    pom_url: Mapped[str | None] = mapped_column(Text)
    is_latest: Mapped[bool] = mapped_column(default=False)
    is_current: Mapped[bool] = mapped_column(default=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    scraped_at: Mapped[str] = mapped_column(Text, default=_now)

    library: Mapped["Library"] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint("library_id", "version", name="uq_lib_version"),
        Index("idx_libver_library", "library_id"),
    )

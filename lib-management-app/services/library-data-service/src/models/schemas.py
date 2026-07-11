"""
Pydantic v2 DTOs — strict separation between ORM models and API contracts.
Request models validate input; Response models define what is sent over the wire.
"""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl


# ── Shared ────────────────────────────────────────────────────────────────────
class OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ══════════════════════════════════════════════════════════════════════════════
# LIBRARY
# ══════════════════════════════════════════════════════════════════════════════

class LibraryResponse(OrmBase):
    id: int
    sl_no: int | None
    package: str
    sdk_name: str | None
    platform: str
    current_version: str | None
    latest_version: str | None
    update_needed: str
    priority: str | None
    repo_url: str | None
    registry: str | None
    comments: str | None
    deprecation_notes: str | None
    status: str
    source_date: str | None
    last_checked_date: str | None
    alert_priority: str
    deadline_date: str | None
    deadline_notes: str | None
    ecosystem: str
    framework_language: str | None
    created_at: str
    updated_at: str


class LibraryListResponse(OrmBase):
    libraries: list[LibraryResponse]
    total: int
    skip: int
    limit: int


class LibraryUpdate(BaseModel):
    """Fields that can be updated by other services or Admin."""
    current_version: str | None = None
    latest_version: str | None = None
    update_needed: Literal[
        "Mandatory", "Recommended", "Optional", "None",
        "critical", "high", "moderate", "low", "none",
    ] | None = None
    priority: str | None = None
    comments: str | None = None
    deprecation_notes: str | None = None
    status: Literal["Active", "Inactive", "Deprecated", "Legacy", "Maintenance", "Unknown"] | None = None
    last_checked_date: str | None = None
    alert_priority: Literal["Normal", "High", "Critical"] | None = None
    deadline_date: str | None = None
    deadline_notes: str | None = None
    ecosystem: str | None = None
    framework_language: str | None = None


class LibraryUpdateRequest(LibraryUpdate):
    """Includes audit fields required when Admin updates via UI."""
    updated_by: str = Field(..., description="Username of person making the change")
    reason: str | None = Field(None, description="Reason for update (written to audit log)")


class SetCurrentVersionRequest(BaseModel):
    """Request payload for setting a selected historical version as current active."""
    version: str = Field(..., min_length=1, description="Version string chosen from history")
    updated_by: str = Field(..., min_length=1, description="Username performing the action")
    reason: str | None = Field(default="Current version set from Version History")


class SetCurrentVersionResponse(BaseModel):
    """Response payload for set current version action."""
    library_id: int
    current_version: str
    status: str


class LibraryCreate(BaseModel):
    """Payload to create a new library record (Admin only)."""
    package: str = Field(..., min_length=1, description="Package identifier, e.g. com.squareup.retrofit2:retrofit")
    sdk_name: str | None = Field(None, description="Human-readable name, e.g. Retrofit")
    platform: Literal["Android", "iOS", "Both"]
    current_version: str | None = None
    latest_version: str | None = None
    update_needed: Literal["mandatory", "recommended", "optional", "none"] = "none"
    priority: Literal["High", "Medium", "Low"] = "Medium"
    repo_url: str | None = None
    registry: str | None = None
    comments: str | None = None
    deprecation_notes: str | None = None
    status: Literal["Active", "Inactive", "Deprecated", "Legacy", "Maintenance", "Unknown"] = "Active"
    alert_priority: Literal["Normal", "High", "Critical"] = "Normal"
    deadline_date: str | None = None
    deadline_notes: str | None = None
    ecosystem: str = "mobile"
    framework_language: str | None = None
    created_by: str | None = None


# ── Filters ───────────────────────────────────────────────────────────────────
class LibraryFilter(BaseModel):
    platform: str | None = None         # Android | iOS | Both
    status: str | None = None           # Active | Deprecated | Legacy
    update_needed: str | None = None    # Mandatory | Recommended | None
    ecosystem: str | None = None        # mobile | web | backend
    alert_priority: str | None = None   # Normal | High | Critical
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=1000)


# ══════════════════════════════════════════════════════════════════════════════
# VERSION HISTORY
# ══════════════════════════════════════════════════════════════════════════════

class VersionHistoryResponse(OrmBase):
    id: int
    library_id: int
    version_number: str
    record_type: str
    source: str | None
    notes: str | None
    recorded_at: str


class VersionHistoryCreate(BaseModel):
    library_id: int
    version_number: str
    record_type: Literal["current", "latest", "previous"]
    source: str | None = None
    notes: str | None = None


# ══════════════════════════════════════════════════════════════════════════════
# RECOMMENDATION
# ══════════════════════════════════════════════════════════════════════════════

class RecommendationResponse(OrmBase):
    id: int
    library_id: int
    priority: str | None
    upgrade_recommended: str | None
    recommendation_summary: str | None
    upgrade_pros: list[str] = Field(default_factory=list)
    upgrade_cons: list[str] = Field(default_factory=list)
    no_upgrade_pros: list[str] = Field(default_factory=list)
    no_upgrade_cons: list[str] = Field(default_factory=list)
    generated_at: str

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_with_json(cls, obj: object) -> "RecommendationResponse":
        """Parse JSON-stored pros/cons lists from ORM model."""
        import json
        def _parse(val: str | None) -> list[str]:
            if not val:
                return []
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return [val] if val else []

        return cls(
            id=obj.id,  # type: ignore[attr-defined]
            library_id=obj.library_id,  # type: ignore[attr-defined]
            priority=obj.priority,  # type: ignore[attr-defined]
            upgrade_recommended=obj.upgrade_recommended,  # type: ignore[attr-defined]
            recommendation_summary=obj.recommendation_summary,  # type: ignore[attr-defined]
            upgrade_pros=_parse(obj.upgrade_pros),  # type: ignore[attr-defined]
            upgrade_cons=_parse(obj.upgrade_cons),  # type: ignore[attr-defined]
            no_upgrade_pros=_parse(obj.no_upgrade_pros),  # type: ignore[attr-defined]
            no_upgrade_cons=_parse(obj.no_upgrade_cons),  # type: ignore[attr-defined]
            generated_at=obj.generated_at,  # type: ignore[attr-defined]
        )


class RecommendationCreate(BaseModel):
    library_id: int
    priority: Literal["critical", "high", "moderate", "low", "none", "manual_review"] | None = None
    upgrade_recommended: Literal["Yes", "No", "Sufficient"]
    recommendation_summary: str
    upgrade_pros: list[str] = Field(default_factory=list)
    upgrade_cons: list[str] = Field(default_factory=list)
    no_upgrade_pros: list[str] = Field(default_factory=list)
    no_upgrade_cons: list[str] = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════════════
# UPGRADE LIFECYCLE (B1)
# ══════════════════════════════════════════════════════════════════════════════

class LifecycleResponse(OrmBase):
    id: int
    library_id: int
    recommendation_id: int | None
    status: str
    target_version: str | None
    target_sprint: str | None
    target_date: str | None
    completed_version: str | None
    skip_reason: str | None
    actioned_by: str | None
    created_at: str
    updated_at: str


class LifecycleUpdate(BaseModel):
    status: Literal["Acknowledged", "Scheduled", "In Progress", "Completed", "Skipped"] | None = None
    target_version: str | None = None
    target_sprint: str | None = None
    target_date: str | None = None
    completed_version: str | None = None
    skip_reason: str | None = None
    actioned_by: str = Field(..., description="Username")


class LifecycleSetActiveRequest(BaseModel):
    """
    Marks a library version as the active/current version (Completed lifecycle).
    Comment is mandatory — used as audit trail reason.
    """
    target_version: str = Field(..., min_length=1, description="Version being activated")
    comment: str = Field(..., min_length=1, description="Mandatory reason / deployment note")
    actioned_by: str = Field(..., min_length=1, description="Username")


# ══════════════════════════════════════════════════════════════════════════════
# EXTERNAL SOURCES
# ══════════════════════════════════════════════════════════════════════════════

class ExternalSourceResponse(OrmBase):
    id: int
    library_id: int
    source_name: str
    url: str
    source_type: str
    added_by: str
    is_active: int
    created_at: str


class ExternalSourceCreate(BaseModel):
    source_name: str
    url: str = Field(..., description="Must be a valid URL")
    source_type: Literal["registry", "release_notes", "changelog", "docs", "custom"] = "custom"
    added_by: str


# ══════════════════════════════════════════════════════════════════════════════
# SCRAPE CACHE (T1)
# ══════════════════════════════════════════════════════════════════════════════

class ScrapeCacheResponse(OrmBase):
    library_id: int
    registry_key: str
    scraped_version: str
    release_notes: str | None
    expires_at: str
    scraped_at: str
    is_expired: bool = False


class ScrapeCacheUpsert(BaseModel):
    library_id: int
    registry_key: str
    scraped_version: str
    release_notes: str | None = None
    raw_response: str | None = None
    ttl_hours: int = Field(default=6, ge=1, le=168)


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE RUNS
# ══════════════════════════════════════════════════════════════════════════════

class PipelineRunCreate(BaseModel):
    run_id: str
    triggered_by: Literal["scheduler", "manual"]


class PipelineRunUpdate(BaseModel):
    status: Literal["running", "completed", "partial", "failed"]
    libraries_processed: int | None = None
    libraries_updated: int | None = None
    errors_count: int | None = None
    finished_at: str | None = None
    steps_json: str | None = None  # JSON-serialized full step results


class PipelineRunDetailCreate(BaseModel):
    run_id: str
    library_id: int | None = None
    step: Literal["scrape", "compare", "recommend", "notify", "cleanup", "backup"]
    status: Literal["success", "failed", "skipped"]
    message: str | None = None


class PipelineRunResponse(OrmBase):
    run_id: str
    triggered_by: str
    status: str
    libraries_processed: int
    libraries_updated: int
    errors_count: int
    started_at: str
    finished_at: str | None
    steps_json: str | None = None  # JSON-serialized full step results


class PipelineRunDetailResponse(OrmBase):
    id: int
    run_id: str
    library_id: int | None
    step: str
    status: str
    message: str | None
    recorded_at: str


class PipelineRunWithDetailsResponse(BaseModel):
    run_id: str
    triggered_by: str
    status: str
    libraries_processed: int
    libraries_updated: int
    errors_count: int
    started_at: str
    finished_at: str | None
    details: list[PipelineRunDetailResponse] = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════════════
# NOTIFICATION
# ══════════════════════════════════════════════════════════════════════════════

class NotificationCreate(BaseModel):
    library_id: int | None = None
    notification_type: Literal["Email", "Teams", "Both"]
    content: str


class NotificationUpdate(BaseModel):
    status: Literal["Pending", "Sent", "Failed"]
    sent_at: str | None = None


class NotificationSentLogCreate(BaseModel):
    library_id: int
    notification_id: int | None = None
    latest_version_at_send: str | None = None
    update_needed_at_send: str | None = None
    status_at_send: str | None = None
    content_hash: str


# ══════════════════════════════════════════════════════════════════════════════
# LLM USAGE LOG (T5)
# ══════════════════════════════════════════════════════════════════════════════

class LLMUsageCreate(BaseModel):
    run_id: str | None = None
    library_id: int | None = None
    prompt_key: str | None = None
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    latency_ms: int | None = None


class LLMUsageLogResponse(OrmBase):
    id: int
    run_id: str | None
    library_id: int | None
    prompt_key: str | None
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    latency_ms: int | None
    logged_at: str


class LLMUsageStats(BaseModel):
    total_calls: int
    total_tokens: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_cost_usd: float
    avg_latency_ms: float | None
    models_used: list[str]
    calls_this_month: int
    cost_this_month: float


# ── Audit Trail ───────────────────────────────────────────────────────────────

class AuditLogResponse(OrmBase):
    id: int
    library_id: int
    updated_by: str
    update_type: str
    field_changed: str
    old_value: str | None
    new_value: str | None
    reason: str | None
    updated_at: str
    package: str | None = None      # denormalised for display
    sdk_name: str | None = None     # denormalised for display


# ── Lifecycle with Library info ───────────────────────────────────────────────

class LifecycleWithLibraryResponse(BaseModel):
    id: int
    library_id: int
    recommendation_id: int | None
    status: str
    target_version: str | None
    target_sprint: str | None
    target_date: str | None
    completed_version: str | None
    skip_reason: str | None
    actioned_by: str | None
    created_at: str
    updated_at: str
    # library fields
    package: str | None = None
    sdk_name: str | None = None
    platform: str | None = None
    current_version: str | None = None
    latest_version: str | None = None
    update_needed: str | None = None
    priority: str | None = None
    business_critical: bool | None = None
    confidence_score: int | None = None
    confidence_band: Literal["High", "Medium", "Low"] | None = None


class LifecycleInitRequest(BaseModel):
    """Create/initialise a lifecycle entry for a library."""
    library_id: int
    recommendation_id: int | None = None
    actioned_by: str
    target_version: str | None = None


class LifecycleBatchReviewRequest(BaseModel):
    """Batch-create awaiting_review lifecycle entries after pipeline run."""
    run_id: str
    libraries: list[dict]   # each: {library_id, recommendation, update_needed, summary}


class LifecycleCompleteRequest(BaseModel):
    """Mark lifecycle as Completed — also updates library current_version."""
    completed_version: str = Field(..., min_length=1)
    actioned_by: str
    pr_url: str | None = None
    reason: str | None = None

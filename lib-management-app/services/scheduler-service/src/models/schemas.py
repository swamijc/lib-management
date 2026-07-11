"""Scheduler Service — Pydantic v2 DTOs."""
from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"          # some steps failed, others succeeded


class StepName(str, Enum):
    FETCH_LIBRARIES       = "fetch_libraries"
    BATCH_SCRAPE          = "batch_scrape"
    FETCH_VERSION_HISTORY = "fetch_version_history"
    BATCH_COMPARE         = "batch_compare"
    BATCH_RECOMMEND       = "batch_recommend"
    CHECK_DEADLINES       = "check_deadlines"
    NOTIFY                = "notify"


class StepResult(BaseModel):
    step: StepName
    status: PipelineStatus
    message: str = ""
    items_processed: int = 0
    duration_seconds: float = 0.0
    started_at: datetime = Field(default_factory=_utcnow)
    finished_at: datetime | None = None

    model_config = {"use_enum_values": True}


class PipelineRun(BaseModel):
    run_id: str
    triggered_by: str = "scheduler"   # "scheduler" | "manual"
    status: PipelineStatus
    steps: list[StepResult] = []
    total_libraries: int = 0
    started_at: datetime = Field(default_factory=_utcnow)
    finished_at: datetime | None = None
    error: str | None = None

    model_config = {"use_enum_values": True}


class ScheduleConfig(BaseModel):
    cron: str
    enabled: bool
    next_run: datetime | None = None
    last_run: datetime | None = None


class ScheduleUpdateRequest(BaseModel):
    cron: str = Field(..., description="Cron expression e.g. '0 8 * * 1-5'")
    enabled: bool = True


class RetryRunRequest(BaseModel):
    source_run_id: str
    step: StepName


class RetryRunResponse(BaseModel):
    request_status: str  # queued | rejected
    message: str
    run_id: str | None = None
    source_run_id: str | None = None
    step: StepName | None = None

    model_config = {"use_enum_values": True}

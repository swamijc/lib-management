"""
Scheduler Service — routers.

Endpoints:
  GET  /api/v1/schedule       — view current schedule config
  PUT  /api/v1/schedule       — update cron + enabled flag
  POST /api/v1/run/now        — trigger manual pipeline run (async)
    POST /api/v1/run/retry      — retry a single failed stage (new run)
    POST /api/v1/run/retry-from-here — retry pipeline from selected stage (new run)
  GET  /api/v1/runs           — list run history
  GET  /api/v1/runs/{run_id}  — get one run
"""
from __future__ import annotations
import asyncio

from fastapi import APIRouter, BackgroundTasks, HTTPException

from ..config import settings
from ..models.schemas import (
    PipelineRun,
    RetryRunRequest,
    RetryRunResponse,
    ScheduleConfig,
    ScheduleUpdateRequest,
)
from ..services.scheduler_service import SchedulerService
from shared.models.base_schemas import ApiResponse, ResponseMeta

router = APIRouter(prefix="/api/v1", tags=["scheduler"])

# Single service instance shared across requests
_svc: SchedulerService | None = None


def get_service() -> SchedulerService:
    global _svc
    if _svc is None:
        _svc = SchedulerService()
    return _svc


def _meta() -> ResponseMeta:
    return ResponseMeta(service=settings.service_name, version=settings.service_version)


@router.get("/schedule", response_model=ApiResponse[ScheduleConfig])
async def get_schedule() -> ApiResponse[ScheduleConfig]:
    """Return current schedule configuration."""
    return ApiResponse.ok(data=get_service().get_schedule(), meta=_meta())


@router.put("/schedule", response_model=ApiResponse[ScheduleConfig])
async def update_schedule(req: ScheduleUpdateRequest) -> ApiResponse[ScheduleConfig]:
    """Update cron expression and enabled state."""
    config = get_service().update_schedule(req)
    return ApiResponse.ok(data=config, meta=_meta())


@router.post("/run/now", response_model=ApiResponse[PipelineRun])
async def run_now(background_tasks: BackgroundTasks) -> ApiResponse[PipelineRun]:
    """
    Trigger a manual pipeline run immediately.
    The run starts in the background; the response returns immediately with a
    run_id that can be polled via GET /runs/{run_id}.
    """
    svc = get_service()
    run = svc.queue_run(triggered_by="manual")
    background_tasks.add_task(_run_in_background, svc, run.run_id, "manual")
    return ApiResponse.ok(data=run, meta=_meta())


@router.post("/run/retry", response_model=ApiResponse[RetryRunResponse])
async def retry_stage(req: RetryRunRequest, background_tasks: BackgroundTasks) -> ApiResponse[RetryRunResponse]:
    """Queue a new pipeline run tagged as a stage retry."""
    svc = get_service()

    source = svc.get_run(req.source_run_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Run '{req.source_run_id}' not found")

    step_exists = any(str(s.step) == str(req.step) for s in source.steps)
    if not step_exists:
        raise HTTPException(status_code=400, detail=f"Step '{req.step}' not found in run '{req.source_run_id}'")

    if svc.is_pipeline_running():
        current = svc.latest_running_run()
        return ApiResponse.ok(
            data=RetryRunResponse(
                request_status="rejected",
                message="Pipeline is already running. Retry request rejected.",
                run_id=current.run_id if current else None,
                source_run_id=req.source_run_id,
                step=req.step,
            ),
            meta=_meta(),
        )

    triggered_by = f"retry_stage:{req.step}"
    run = svc.queue_run(triggered_by=triggered_by)
    background_tasks.add_task(_run_in_background, svc, run.run_id, triggered_by)
    return ApiResponse.ok(
        data=RetryRunResponse(
            request_status="queued",
            message=f"Retry queued for stage '{req.step}'",
            run_id=run.run_id,
            source_run_id=req.source_run_id,
            step=req.step,
        ),
        meta=_meta(),
    )


@router.post("/run/retry-from-here", response_model=ApiResponse[RetryRunResponse])
async def retry_from_here(req: RetryRunRequest, background_tasks: BackgroundTasks) -> ApiResponse[RetryRunResponse]:
    """Queue a new pipeline run tagged as retry-from-stage."""
    svc = get_service()

    source = svc.get_run(req.source_run_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Run '{req.source_run_id}' not found")

    step_exists = any(str(s.step) == str(req.step) for s in source.steps)
    if not step_exists:
        raise HTTPException(status_code=400, detail=f"Step '{req.step}' not found in run '{req.source_run_id}'")

    if svc.is_pipeline_running():
        current = svc.latest_running_run()
        return ApiResponse.ok(
            data=RetryRunResponse(
                request_status="rejected",
                message="Pipeline is already running. Retry-from-here request rejected.",
                run_id=current.run_id if current else None,
                source_run_id=req.source_run_id,
                step=req.step,
            ),
            meta=_meta(),
        )

    triggered_by = f"retry_from:{req.step}"
    run = svc.queue_run(triggered_by=triggered_by)
    background_tasks.add_task(_run_in_background, svc, run.run_id, triggered_by)
    return ApiResponse.ok(
        data=RetryRunResponse(
            request_status="queued",
            message=f"Retry-from-here queued from stage '{req.step}'",
            run_id=run.run_id,
            source_run_id=req.source_run_id,
            step=req.step,
        ),
        meta=_meta(),
    )


async def _run_in_background(svc: SchedulerService, run_id: str, triggered_by: str) -> None:
    """Background task: execute pipeline and update the existing run record."""
    from ..services.scheduler_service import _run_history

    # Find and update the pre-created run record
    existing = next((r for r in _run_history if r.run_id == run_id), None)
    if existing:
        result = await svc.run_pipeline(triggered_by=triggered_by)
        # Copy fields back to the pre-created record
        existing.status = result.status
        existing.steps = result.steps
        existing.total_libraries = result.total_libraries
        existing.finished_at = result.finished_at
        existing.error = result.error


@router.get("/runs", response_model=ApiResponse[list[PipelineRun]])
async def list_runs() -> ApiResponse[list[PipelineRun]]:
    """Return pipeline run history (most recent first)."""
    return ApiResponse.ok(data=get_service().list_runs(), meta=_meta())


@router.get("/runs/{run_id}", response_model=ApiResponse[PipelineRun])
async def get_run(run_id: str) -> ApiResponse[PipelineRun]:
    """Return a specific pipeline run by ID."""
    run = get_service().get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return ApiResponse.ok(data=run, meta=_meta())

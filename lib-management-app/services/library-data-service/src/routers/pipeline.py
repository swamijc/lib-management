"""Router: /api/v1/pipeline-runs"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models.schemas import (
    PipelineRunCreate, PipelineRunDetailCreate, PipelineRunResponse,
    PipelineRunUpdate, PipelineRunWithDetailsResponse, PipelineRunDetailResponse,
)
from ..repositories.other_repos import PipelineRunRepository
from shared.models.base_schemas import ApiResponse, ResponseMeta

router = APIRouter(prefix="/api/v1/pipeline-runs", tags=["pipeline-runs"])


def _meta() -> ResponseMeta:
    return ResponseMeta(service=settings.service_name, version=settings.service_version)


@router.get("", response_model=ApiResponse[list[PipelineRunResponse]])
async def list_runs(limit: int = 50, db: AsyncSession = Depends(get_db)):
    repo = PipelineRunRepository(db)
    runs = await repo.get_all(limit)
    return ApiResponse.ok(data=[PipelineRunResponse.model_validate(r) for r in runs], meta=_meta())


@router.get("/active", response_model=ApiResponse[PipelineRunResponse | None])
async def get_active(db: AsyncSession = Depends(get_db)):
    """T2: check if pipeline is already running."""
    repo = PipelineRunRepository(db)
    run = await repo.get_active()
    return ApiResponse.ok(data=PipelineRunResponse.model_validate(run) if run else None, meta=_meta())


@router.post("", response_model=ApiResponse[PipelineRunResponse])
async def create_run(data: PipelineRunCreate, db: AsyncSession = Depends(get_db)):
    repo = PipelineRunRepository(db)
    run = await repo.create(data)
    return ApiResponse.ok(data=PipelineRunResponse.model_validate(run), meta=_meta())


@router.put("/{run_id}", response_model=ApiResponse[PipelineRunResponse])
async def update_run(run_id: str, data: PipelineRunUpdate, db: AsyncSession = Depends(get_db)):
    repo = PipelineRunRepository(db)
    run = await repo.update(run_id, data)
    if run is None:
        return ApiResponse.fail(code="RUN_NOT_FOUND", message=f"run_id={run_id} not found", meta=_meta())
    return ApiResponse.ok(data=PipelineRunResponse.model_validate(run), meta=_meta())


@router.post("/{run_id}/details")
async def add_detail(run_id: str, data: PipelineRunDetailCreate, db: AsyncSession = Depends(get_db)):
    data.run_id = run_id
    repo = PipelineRunRepository(db)
    detail = await repo.add_detail(data)
    return ApiResponse.ok(data={"id": detail.id}, meta=_meta())


@router.post("/{run_id}/details/batch")
async def add_details_batch(
    run_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    """
    Bulk-insert per-library step details.
    payload: {"step": str, "details": [{"library_id": int, "status": str, "message": str}]}
    """
    from ..models.orm import PipelineRunDetail
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    step   = payload.get("step", "unknown")
    items  = payload.get("details", [])
    added  = 0
    for item in items:
        db.add(PipelineRunDetail(
            run_id=run_id,
            library_id=item.get("library_id"),
            step=step,
            status=item.get("status", "success"),
            message=item.get("message", ""),
            recorded_at=now,
        ))
        added += 1
    await db.commit()
    return ApiResponse.ok(data={"run_id": run_id, "step": step, "added": added}, meta=_meta())


@router.get("/{run_id}", response_model=ApiResponse[PipelineRunWithDetailsResponse])
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from ..models.orm import PipelineRun, PipelineRunDetail
    repo = PipelineRunRepository(db)
    run = await repo.get_by_run_id(run_id)
    if run is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    details_result = await db.execute(
        select(PipelineRunDetail)
        .where(PipelineRunDetail.run_id == run_id)
        .order_by(PipelineRunDetail.recorded_at)
    )
    details = details_result.scalars().all()
    return ApiResponse.ok(
        data=PipelineRunWithDetailsResponse(
            run_id=run.run_id,
            triggered_by=run.triggered_by,
            status=run.status,
            libraries_processed=run.libraries_processed,
            libraries_updated=run.libraries_updated,
            errors_count=run.errors_count,
            started_at=run.started_at,
            finished_at=run.finished_at,
            details=[PipelineRunDetailResponse.model_validate(d) for d in details],
        ),
        meta=_meta(),
    )


@router.delete("/history/cleanup", response_model=ApiResponse[dict])
async def cleanup_history(
    retention_days: int = 30,
    include_partial: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """
    Permanently delete old pipeline history records from DB.
    Business default: delete completed/failed/partial runs older than 30 days.
    """
    if retention_days < 7 or retention_days > 365:
        raise HTTPException(status_code=400, detail="retention_days must be between 7 and 365")

    repo = PipelineRunRepository(db)
    deleted = await repo.purge_history(retention_days=retention_days, include_partial=include_partial)
    await db.commit()
    return ApiResponse.ok(
        data={
            "retention_days": retention_days,
            "include_partial": include_partial,
            **deleted,
        },
        meta=_meta(),
    )

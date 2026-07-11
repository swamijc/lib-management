"""
Scheduler Service — pipeline runner + APScheduler integration.

Manages:
  - Running the 5-step pipeline (fetch → scrape → compare → recommend → notify)
  - APScheduler cron job for scheduled runs
  - Run history persisted to library-data-service DB (survives restarts)
"""
from __future__ import annotations
import json
import uuid
from collections import deque
from datetime import datetime, timezone

import httpx
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ..config import settings
from ..models.schemas import (
    PipelineRun,
    PipelineStatus,
    ScheduleConfig,
    ScheduleUpdateRequest,
    StepName,
    StepResult,
)
from ..pipeline.steps import (
    step_batch_compare,
    step_batch_recommend,
    step_batch_scrape,
    step_check_deadlines,
    step_fetch_libraries,
    step_fetch_version_history,
    step_notify,
)

logger = structlog.get_logger(__name__)

# Rolling history of last 50 runs (in-memory; populated from DB on startup)
_run_history: deque[PipelineRun] = deque(maxlen=50)

# Lock to prevent concurrent pipeline runs (T2 gap equivalent)
_pipeline_running: bool = False

_LIB_SVC = None  # set lazily
_HEADERS_FN = lambda: {"X-Internal-Service-Key": settings.internal_service_key}  # noqa: E731


async def _persist_run_start(run: PipelineRun) -> None:
    """Create a DB record for this run immediately when it starts."""
    try:
        async with httpx.AsyncClient(timeout=5.0, verify=False) as c:
            r = await c.post(
                f"{settings.library_data_service_url}/api/v1/pipeline-runs",
                json={"run_id": run.run_id, "triggered_by": run.triggered_by},
                headers=_HEADERS_FN(),
            )
            if r.status_code not in (200, 201):
                logger.warning("persist_run_start_failed", status=r.status_code, body=r.text[:200])
    except Exception as exc:
        logger.warning("persist_run_start_failed", error=str(exc)[:80])


async def _persist_run_finish(run: PipelineRun) -> None:
    """Update the DB record when the run finishes with full steps + status."""
    failed_steps = [s for s in run.steps if s.status == PipelineStatus.FAILED]
    errors_count = len(failed_steps)
    libs_processed = run.total_libraries or 0

    # Serialize the full step list so it survives restarts
    steps_json = json.dumps([
        {
            "step": s.step, "status": s.status, "message": s.message,
            "items_processed": s.items_processed,
            "duration_seconds": s.duration_seconds,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "finished_at": s.finished_at.isoformat() if s.finished_at else None,
        }
        for s in run.steps
    ])

    try:
        async with httpx.AsyncClient(timeout=5.0, verify=False) as c:
            r = await c.put(
                f"{settings.library_data_service_url}/api/v1/pipeline-runs/{run.run_id}",
                json={
                    "status": run.status,
                    "libraries_processed": libs_processed,
                    "errors_count": errors_count,
                    "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                    "steps_json": steps_json,
                },
                headers=_HEADERS_FN(),
            )
            if r.status_code != 200:
                logger.warning("persist_run_finish_failed", status=r.status_code, body=r.text[:200])
    except Exception as exc:
        logger.warning("persist_run_finish_failed", error=str(exc)[:80])


async def load_run_history_from_db() -> None:
    """Called on startup: load the last 50 runs from DB into _run_history.
    Only loads runs that have steps_json (real runs with data)."""
    try:
        async with httpx.AsyncClient(timeout=8.0, verify=False) as c:
            resp = await c.get(
                f"{settings.library_data_service_url}/api/v1/pipeline-runs?limit=50",
                headers=_HEADERS_FN(),
            )
            if resp.status_code != 200:
                return
        db_runs = resp.json().get("data", [])
        loaded = 0
        for r in reversed(db_runs):  # oldest first so deque order is correct
            # Skip stale running entries and orphaned records with no step data
            if r.get("status") == "running":
                continue
            if not r.get("steps_json"):
                continue  # skip ghost records with no real step data
            steps: list[StepResult] = []
            try:
                raw = json.loads(r["steps_json"])
                for s in raw:
                    steps.append(StepResult(
                        step=s["step"],
                        status=s["status"],
                        message=s.get("message", ""),
                        items_processed=s.get("items_processed", 0),
                        duration_seconds=s.get("duration_seconds", 0.0),
                        started_at=datetime.fromisoformat(s["started_at"]) if s.get("started_at") else datetime.now(timezone.utc),
                        finished_at=datetime.fromisoformat(s["finished_at"]) if s.get("finished_at") else None,
                    ))
            except Exception:
                pass

            _run_history.append(PipelineRun(
                run_id=r["run_id"],
                triggered_by=r.get("triggered_by", "scheduler"),
                status=r["status"],
                steps=steps,
                total_libraries=r.get("libraries_processed", 0),
                started_at=datetime.fromisoformat(r["started_at"]) if r.get("started_at") else datetime.now(timezone.utc),
                finished_at=datetime.fromisoformat(r["finished_at"]) if r.get("finished_at") else None,
            ))
            loaded += 1
        logger.info("run_history_loaded_from_db", count=loaded)
    except Exception as exc:
        logger.warning("load_run_history_failed", error=str(exc)[:80])


class SchedulerService:

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._cron = settings.schedule_cron
        self._enabled = settings.schedule_enabled

    # ── APScheduler lifecycle ─────────────────────────────────────────────────

    def start(self) -> None:
        if self._enabled:
            self._add_job()
        self._scheduler.start()
        logger.info("scheduler_started", cron=self._cron, enabled=self._enabled)

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)
        logger.info("scheduler_stopped")

    def _add_job(self) -> None:
        self._scheduler.add_job(
            self._run_scheduled,
            CronTrigger.from_crontab(self._cron),
            id="pipeline",
            replace_existing=True,
        )

    async def _run_scheduled(self) -> None:
        await self.run_pipeline(triggered_by="scheduler")

    # ── Schedule management ───────────────────────────────────────────────────

    def get_schedule(self) -> ScheduleConfig:
        job = self._scheduler.get_job("pipeline")
        next_run: datetime | None = None
        if job and job.next_run_time:
            next_run = job.next_run_time

        last_run: datetime | None = None
        if _run_history:
            last_run = _run_history[-1].started_at

        return ScheduleConfig(
            cron=self._cron,
            enabled=self._enabled,
            next_run=next_run,
            last_run=last_run,
        )

    def update_schedule(self, req: ScheduleUpdateRequest) -> ScheduleConfig:
        self._cron = req.cron
        self._enabled = req.enabled
        if req.enabled:
            self._add_job()
        else:
            if self._scheduler.get_job("pipeline"):
                self._scheduler.remove_job("pipeline")
        logger.info("schedule_updated", cron=req.cron, enabled=req.enabled)
        return self.get_schedule()

    def is_pipeline_running(self) -> bool:
        return _pipeline_running

    def latest_running_run(self) -> PipelineRun | None:
        return next(
            (r for r in reversed(_run_history) if r.status == PipelineStatus.RUNNING),
            None,
        )

    def queue_run(self, triggered_by: str) -> PipelineRun:
        run = PipelineRun(
            run_id=str(uuid.uuid4()),
            triggered_by=triggered_by,
            status=PipelineStatus.PENDING,
        )
        _run_history.append(run)
        return run

    # ── Pipeline runner ───────────────────────────────────────────────────────

    async def run_pipeline(self, triggered_by: str = "manual") -> PipelineRun:
        global _pipeline_running
        if _pipeline_running:
            logger.warning("pipeline_already_running")
            # Return the most-recent in-progress run rather than starting a new one
            in_progress = next(
                (r for r in reversed(_run_history) if r.status == PipelineStatus.RUNNING),
                None,
            )
            if in_progress:
                return in_progress
            # Fallback: create a dummy rejected run
            return PipelineRun(
                run_id=str(uuid.uuid4()),
                triggered_by=triggered_by,
                status=PipelineStatus.FAILED,
                error="Pipeline already running — request rejected",
            )

        _pipeline_running = True
        run = PipelineRun(
            run_id=str(uuid.uuid4()),
            triggered_by=triggered_by,
            status=PipelineStatus.RUNNING,
        )
        _run_history.append(run)
        logger.info("pipeline_start", run_id=run.run_id, triggered_by=triggered_by)

        # Persist run record to DB immediately so it survives restarts
        await _persist_run_start(run)

        ctx: dict = {}
        step_fns = [
            step_fetch_libraries,
            step_batch_scrape,
            step_fetch_version_history,
            step_batch_compare,
            step_batch_recommend,
            step_check_deadlines,
            step_notify,
        ]

        try:
            for fn in step_fns:
                step_result = await fn(ctx)
                run.steps.append(step_result)
                if step_result.status == PipelineStatus.FAILED and fn == step_fetch_libraries:
                    # Can't proceed without library data
                    run.status = PipelineStatus.FAILED
                    run.error = f"Pipeline aborted: {step_result.message}"
                    break
            else:
                # All steps executed — determine overall status
                failed_steps = [s for s in run.steps if s.status == PipelineStatus.FAILED]
                if not failed_steps:
                    run.status = PipelineStatus.COMPLETED
                elif len(failed_steps) == len(run.steps):
                    run.status = PipelineStatus.FAILED
                else:
                    run.status = PipelineStatus.PARTIAL

                libs = ctx.get("libraries", [])
                run.total_libraries = len(libs)

                # Write per-library details to library-data-service (best-effort)
                await _store_run_details(run.run_id, ctx)

        except Exception as exc:
            run.status = PipelineStatus.FAILED
            run.error = str(exc)
            logger.error("pipeline_error", run_id=run.run_id, error=str(exc))
        finally:
            run.finished_at = datetime.now(timezone.utc)
            _pipeline_running = False
            # Persist final status + full steps to DB so history survives restarts
            await _persist_run_finish(run)

        logger.info(
            "pipeline_finish",
            run_id=run.run_id,
            status=run.status,
            libraries=run.total_libraries,
        )
        return run

    def list_runs(self) -> list[PipelineRun]:
        return list(reversed(_run_history))  # most recent first

    def get_run(self, run_id: str) -> PipelineRun | None:
        return next((r for r in _run_history if r.run_id == run_id), None)


async def _store_run_details(run_id: str, ctx: dict) -> None:
    """
    Best-effort: persist per-library pipeline results to library-data-service.
    1. Writes recommendations to recommendations table (for HITL review read-back)
    2. Writes per-library step details to pipeline_run_details
    3. Creates awaiting_review lifecycle entries for all libraries
    """
    import httpx as _httpx

    lib_svc = settings.library_data_service_url
    headers = {"X-Internal-Service-Key": settings.internal_service_key}
    libs    = ctx.get("libraries", [])
    cmp_map = {c["library_id"]: c for c in ctx.get("comparison_results", [])}
    rec_map = {r["library_id"]: r for r in ctx.get("recommendation_results", [])}

    logger.info("store_run_details_start", run_id=run_id, libraries=len(libs))

    # 1 ── Persist recommendations to library-data-service DB ────────────────
    try:
        stored_recs = 0
        async with _httpx.AsyncClient(timeout=15.0) as client:
            for lib in libs:
                lid = lib["id"]
                rec = rec_map.get(lid, {})
                if not rec or not rec.get("upgrade_recommended"):
                    continue
                decision = rec.get("upgrade_recommended", "No")
                if decision not in ("Yes", "No", "Sufficient"):
                    decision = "No"
                rec_priority = (rec.get("priority") or "").strip().lower()
                if rec_priority not in ("critical", "high", "moderate", "low", "none", "manual_review"):
                    summary_l = (rec.get("recommendation_summary") or "").lower()
                    if "manual review" in summary_l:
                        rec_priority = "manual_review"
                    elif decision == "Sufficient":
                        rec_priority = "none"
                    else:
                        rec_priority = "manual_review"
                r = await client.post(
                    f"{lib_svc}/api/v1/recommendations",
                    json={
                        "library_id":             lid,
                        "priority":               rec_priority,
                        "upgrade_recommended":    decision,
                        "recommendation_summary": rec.get("recommendation_summary", "") or "",
                        "upgrade_pros":    rec.get("upgrade_pros", []) or [],
                        "upgrade_cons":    rec.get("upgrade_cons", []) or [],
                        "no_upgrade_pros": rec.get("no_upgrade_pros", []) or [],
                        "no_upgrade_cons": rec.get("no_upgrade_cons", []) or [],
                    },
                    headers=headers,
                )
                if r.status_code in (200, 201):
                    stored_recs += 1
        logger.info("recommendations_persisted", count=stored_recs)
    except Exception as exc:
        logger.warning("recommendations_persist_failed", error=str(exc))

    # 2 ── Create pipeline_run record + write per-library step details ────────
    try:
        async with _httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{lib_svc}/api/v1/pipeline-runs",
                json={"run_id": run_id, "triggered_by": "scheduler"},
                headers=headers,
            )
    except Exception:
        pass  # already exists or service unavailable

    fetch_details = [
        {"library_id": lib["id"], "status": "success",
         "message": f"{lib.get('sdk_name') or lib['package']} | {lib.get('platform','')} | {lib.get('update_needed','')}"}
        for lib in libs
    ]
    cmp_details = []
    for lib in libs:
        lid = lib["id"]
        cmp = cmp_map.get(lid, {})
        if cmp:
            newer = cmp.get("new_version_released", False)
            vs    = cmp.get("version_status", "unknown")
            cmp_details.append({
                "library_id": lid, "status": "success",
                "message": f"{lib.get('current_version','?')} → {lib.get('latest_version','?')} | {vs} | {'NEW' if newer else 'same'}",
            })
        else:
            cmp_details.append({"library_id": lid, "status": "skipped", "message": "No version data"})
    rec_details = [
        {"library_id": lib["id"], "status": "success",
         "message": f"AI: {rec_map.get(lib['id'],{}).get('upgrade_recommended','—')} | {(rec_map.get(lib['id'],{}).get('recommendation_summary') or '')[:100]}"}
        for lib in libs
    ]

    try:
        async with _httpx.AsyncClient(timeout=10.0) as client:
            for step_name, details in [
                ("fetch_libraries", fetch_details),
                ("batch_compare",   cmp_details),
                ("batch_recommend", rec_details),
            ]:
                if details:
                    await client.post(
                        f"{lib_svc}/api/v1/pipeline-runs/{run_id}/details/batch",
                        json={"step": step_name, "details": details},
                        headers=headers,
                    )
    except Exception as exc:
        logger.warning("store_run_details_failed", error=str(exc))

    # 3 ── Create awaiting_review HITL lifecycle entries for all libraries ────
    try:
        batch_payload = {
            "run_id": run_id,
            "libraries": [
                {
                    "library_id":     lib["id"],
                    "update_needed":  lib.get("update_needed", ""),
                    "recommendation": rec_map.get(lib["id"], {}).get("upgrade_recommended", ""),
                }
                for lib in libs
            ]
        }
        async with _httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{lib_svc}/api/v1/lifecycle/batch-review",
                json=batch_payload,
                headers=headers,
            )
            if r.status_code in (200, 201):
                result = r.json()
                logger.info("hitl_review_entries_created",
                            created=result.get("created", 0),
                            updated=result.get("updated", 0))
    except Exception as exc:
        logger.warning("hitl_batch_review_failed", error=str(exc))

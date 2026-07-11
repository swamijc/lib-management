"""
Repositories for: Recommendations, Notifications, Pipeline Runs,
Scrape Cache, LLM Usage Log, Upgrade Lifecycle, Notification Sent Log.
"""
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.orm import (
    LLMUsageLog, Notification, NotificationSentLog, PipelineRun,
    PipelineRunDetail, Recommendation, ScrapeCache, UpgradeLifecycle,
)
from ..models.schemas import (
    LLMUsageCreate, NotificationCreate, NotificationSentLogCreate,
    NotificationUpdate, PipelineRunCreate, PipelineRunDetailCreate,
    PipelineRunUpdate, RecommendationCreate,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Recommendation ────────────────────────────────────────────────────────────

class RecommendationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_library(self, library_id: int) -> Recommendation | None:
        result = await self._session.execute(
            select(Recommendation)
            .where(Recommendation.library_id == library_id)
            .order_by(Recommendation.generated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> list[Recommendation]:
        result = await self._session.execute(
            select(Recommendation).order_by(Recommendation.generated_at.desc())
        )
        return result.scalars().all()  # type: ignore[return-value]

    async def create(self, data: RecommendationCreate) -> Recommendation:
        rec = Recommendation(
            library_id=data.library_id,
            priority=data.priority,
            upgrade_recommended=data.upgrade_recommended,
            recommendation_summary=data.recommendation_summary,
            upgrade_pros=json.dumps(data.upgrade_pros),
            upgrade_cons=json.dumps(data.upgrade_cons),
            no_upgrade_pros=json.dumps(data.no_upgrade_pros),
            no_upgrade_cons=json.dumps(data.no_upgrade_cons),
            generated_at=_now(),
        )
        self._session.add(rec)
        await self._session.flush()
        await self._session.refresh(rec)
        return rec


# ── Notification ──────────────────────────────────────────────────────────────

class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_all(self, limit: int = 100) -> list[Notification]:
        result = await self._session.execute(
            select(Notification)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()  # type: ignore[return-value]

    async def create(self, data: NotificationCreate) -> Notification:
        notif = Notification(
            library_id=data.library_id,
            notification_type=data.notification_type,
            content=data.content,
            status="Pending",
            created_at=_now(),
        )
        self._session.add(notif)
        await self._session.flush()
        await self._session.refresh(notif)
        return notif

    async def update_status(self, notification_id: int, data: NotificationUpdate) -> Notification | None:
        notif = await self._session.get(Notification, notification_id)
        if notif is None:
            return None
        notif.status = data.status
        if data.sent_at:
            notif.sent_at = data.sent_at
        await self._session.flush()
        return notif

    async def create_sent_log(self, data: NotificationSentLogCreate) -> NotificationSentLog:
        entry = NotificationSentLog(
            library_id=data.library_id,
            notification_id=data.notification_id,
            latest_version_at_send=data.latest_version_at_send,
            update_needed_at_send=data.update_needed_at_send,
            status_at_send=data.status_at_send,
            content_hash=data.content_hash,
            sent_at=_now(),
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def get_last_sent_hash(self, library_id: int) -> str | None:
        """Returns the last content_hash for this library (B2 dedup logic)."""
        result = await self._session.execute(
            select(NotificationSentLog.content_hash)
            .where(NotificationSentLog.library_id == library_id)
            .order_by(NotificationSentLog.sent_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return row


# ── Pipeline Runs (T2) ───────────────────────────────────────────────────────

class PipelineRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active(self) -> PipelineRun | None:
        """Returns the currently running pipeline, if any (T2 concurrent protection)."""
        result = await self._session.execute(
            select(PipelineRun)
            .where(PipelineRun.status == "running")
            .order_by(PipelineRun.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_all(self, limit: int = 50) -> list[PipelineRun]:
        result = await self._session.execute(
            select(PipelineRun)
            .order_by(PipelineRun.started_at.desc())
            .limit(limit)
        )
        return result.scalars().all()  # type: ignore[return-value]

    async def get_by_run_id(self, run_id: str) -> PipelineRun | None:
        result = await self._session.execute(
            select(PipelineRun).where(PipelineRun.run_id == run_id)
        )
        return result.scalar_one_or_none()

    async def create(self, data: PipelineRunCreate) -> PipelineRun:
        run = PipelineRun(
            run_id=data.run_id,
            triggered_by=data.triggered_by,
            status="running",
            started_at=_now(),
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def update(self, run_id: str, data: PipelineRunUpdate) -> PipelineRun | None:
        run = await self.get_by_run_id(run_id)
        if run is None:
            return None
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(run, field, value)
        if data.status in ("completed", "partial", "failed") and not run.finished_at:
            run.finished_at = _now()
        await self._session.flush()
        return run

    async def add_detail(self, data: PipelineRunDetailCreate) -> PipelineRunDetail:
        detail = PipelineRunDetail(
            run_id=data.run_id,
            library_id=data.library_id,
            step=data.step,
            status=data.status,
            message=data.message,
            recorded_at=_now(),
        )
        self._session.add(detail)
        await self._session.flush()
        return detail

    async def heal_stale_runs(self, threshold_minutes: int = 30) -> int:
        """Marks any 'running' runs older than threshold_minutes as 'failed' (T10)."""
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)).isoformat()
        result = await self._session.execute(
            select(PipelineRun)
            .where(PipelineRun.status == "running")
            .where(PipelineRun.started_at < cutoff)
        )
        stale = result.scalars().all()
        for run in stale:
            run.status = "failed"
            run.finished_at = _now()
        await self._session.flush()
        return len(stale)

    async def purge_history(self, retention_days: int = 30, include_partial: bool = True) -> dict[str, int]:
        """
        Delete old pipeline run history older than retention_days.
        Keeps 'running' rows untouched. Returns deleted counts.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        allowed_statuses = ["completed", "failed"] + (["partial"] if include_partial else [])

        old_runs_result = await self._session.execute(
            select(PipelineRun.run_id)
            .where(PipelineRun.status.in_(allowed_statuses))
            .where(PipelineRun.started_at < cutoff)
        )
        run_ids = [row[0] for row in old_runs_result.all()]
        if not run_ids:
            return {"runs_deleted": 0, "details_deleted": 0}

        # Delete details first, then runs.
        details_del = await self._session.execute(
            delete(PipelineRunDetail).where(PipelineRunDetail.run_id.in_(run_ids))
        )
        runs_del = await self._session.execute(
            delete(PipelineRun).where(PipelineRun.run_id.in_(run_ids))
        )
        await self._session.flush()

        return {
            "runs_deleted": int(runs_del.rowcount or 0),
            "details_deleted": int(details_del.rowcount or 0),
        }


# ── Scrape Cache (T1) ─────────────────────────────────────────────────────────

class ScrapeCacheRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, library_id: int, registry_key: str) -> ScrapeCache | None:
        result = await self._session.execute(
            select(ScrapeCache)
            .where(
                ScrapeCache.library_id == library_id,
                ScrapeCache.registry_key == registry_key,
            )
        )
        return result.scalar_one_or_none()

    async def is_fresh(self, library_id: int, registry_key: str) -> bool:
        """Returns True if a valid non-expired cache entry exists."""
        cache = await self.get(library_id, registry_key)
        if cache is None:
            return False
        return cache.expires_at > _now()

    async def upsert(
        self,
        library_id: int,
        registry_key: str,
        scraped_version: str,
        release_notes: str | None,
        raw_response: str | None,
        ttl_hours: int = 6,
    ) -> ScrapeCache:
        expires_at = (
            datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
        ).isoformat()

        existing = await self.get(library_id, registry_key)
        if existing:
            existing.scraped_version = scraped_version
            existing.release_notes = release_notes
            existing.raw_response = raw_response
            existing.expires_at = expires_at
            existing.scraped_at = _now()
            await self._session.flush()
            return existing

        cache = ScrapeCache(
            library_id=library_id,
            registry_key=registry_key,
            scraped_version=scraped_version,
            release_notes=release_notes,
            raw_response=raw_response,
            expires_at=expires_at,
            scraped_at=_now(),
        )
        self._session.add(cache)
        await self._session.flush()
        return cache


# ── LLM Usage Log (T5) ───────────────────────────────────────────────────────

class LLMUsageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log(self, data: LLMUsageCreate) -> LLMUsageLog:
        entry = LLMUsageLog(
            run_id=data.run_id,
            library_id=data.library_id,
            prompt_key=data.prompt_key,
            model=data.model,
            prompt_tokens=data.prompt_tokens,
            completion_tokens=data.completion_tokens,
            total_tokens=data.total_tokens,
            estimated_cost_usd=data.estimated_cost_usd,
            latency_ms=data.latency_ms,
            logged_at=_now(),
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def get_run_summary(self, run_id: str) -> dict:
        from sqlalchemy import func as sa_func
        result = await self._session.execute(
            select(
                sa_func.sum(LLMUsageLog.total_tokens).label("total_tokens"),
                sa_func.sum(LLMUsageLog.estimated_cost_usd).label("total_cost"),
                sa_func.count().label("calls"),
            ).where(LLMUsageLog.run_id == run_id)
        )
        row = result.one()
        return {
            "total_tokens": row.total_tokens or 0,
            "total_cost_usd": round(row.total_cost or 0.0, 6),
            "calls": row.calls,
        }


# ── Upgrade Lifecycle (B1) ────────────────────────────────────────────────────

class UpgradeLifecycleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_library(self, library_id: int) -> UpgradeLifecycle | None:
        result = await self._session.execute(
            select(UpgradeLifecycle)
            .where(UpgradeLifecycle.library_id == library_id)
            .order_by(UpgradeLifecycle.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def upsert(self, library_id: int, recommendation_id: int | None, target_version: str | None = None) -> UpgradeLifecycle:
        """Create or reset lifecycle entry for a library.
        - If no entry exists: create one with status='Pending'.
        - If entry exists and is active (not Completed/Skipped):
          - same target_version (or empty target_version): keep current workflow state.
          - changed target_version: reset to Pending and clear in-progress/completion fields,
            forcing acknowledgement for the newly selected version.
        - If entry is Completed or Skipped: RESET it to 'Pending' (re-open).
        """
        existing = await self.get_by_library(library_id)
        if existing:
            if existing.status not in ("Completed", "Skipped"):
                if target_version:
                    changed_target = (existing.target_version or "") != target_version
                    if changed_target:
                        existing.status = "Pending"
                        existing.completed_version = None
                        existing.skip_reason = None
                        existing.actioned_by = None
                        existing.target_sprint = None
                        existing.target_date = None
                    existing.target_version = target_version
                    existing.updated_at = _now()
                    await self._session.flush()
                return existing
            # Reset existing entry instead of creating a new row
            existing.status = "Pending"
            existing.completed_version = None
            existing.skip_reason = None
            existing.actioned_by = None
            existing.target_version = target_version
            existing.target_sprint = None
            existing.target_date = None
            existing.updated_at = _now()
            if recommendation_id is not None:
                existing.recommendation_id = recommendation_id
            await self._session.flush()
            return existing
        entry = UpgradeLifecycle(
            library_id=library_id,
            recommendation_id=recommendation_id,
            status="Pending",
            target_version=target_version,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def update_status(
        self, lifecycle_id: int, status: str, actioned_by: str, **kwargs: object
    ) -> UpgradeLifecycle | None:
        entry = await self._session.get(UpgradeLifecycle, lifecycle_id)
        if entry is None:
            return None
        entry.status = status
        entry.actioned_by = actioned_by
        entry.updated_at = _now()
        for k, v in kwargs.items():
            if hasattr(entry, k):
                setattr(entry, k, v)
        await self._session.flush()
        return entry

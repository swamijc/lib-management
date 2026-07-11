"""Health router — GET /health"""
from fastapi import APIRouter, Request
from ..config import settings
from ..routers.scheduler import get_service

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    svc = get_service()
    schedule = svc.get_schedule()
    return {
        "status": "healthy",
        "service": settings.service_name,
        "version": settings.service_version,
        "schedule_enabled": schedule.enabled,
        "schedule_cron": schedule.cron,
        "next_run": schedule.next_run.isoformat() if schedule.next_run else None,
    }


@router.get("/health/runtime")
async def runtime_health(request: Request) -> dict:
    telemetry = getattr(request.app.state, "runtime_telemetry", None)
    if telemetry is None:
        return {"status": "degraded", "service": settings.service_name, "runtime": None}
    return {
        "status": "healthy",
        "service": settings.service_name,
        "version": settings.service_version,
        "runtime": await telemetry.snapshot(top_n=6),
    }

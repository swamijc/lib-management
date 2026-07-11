"""Health router — GET /health"""
from fastapi import APIRouter, Request
from ..config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {
        "status": "healthy",
        "service": settings.service_name,
        "version": settings.service_version,
        "llm_enabled": settings.llm_enabled,
        "llm_provider": settings.llm_provider or "rule-based fallback",
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

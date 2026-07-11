"""Router: /health (unversioned — accessible by Docker health check)"""
import sqlite3
from fastapi import APIRouter, Request
from ..config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    db_ok = False
    try:
        db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
        conn = sqlite3.connect(db_path, timeout=2)
        conn.execute("SELECT COUNT(*) FROM libraries")
        conn.close()
        db_ok = True
    except Exception:
        pass
    return {
        "status": "healthy" if db_ok else "degraded",
        "service": settings.service_name,
        "version": settings.service_version,
        "db_connected": db_ok,
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

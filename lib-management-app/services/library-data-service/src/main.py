"""
Library Data Service — FastAPI application entry point.
"""
from __future__ import annotations
import structlog
from contextlib import asynccontextmanager
from typing import Any
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import settings
from .routers import health, libraries, version_history, recommendations, pipeline, settings as settings_router, audit, lifecycle, llm_analytics, cve, teams, sla, versions as versions_router
from .exceptions import LibraryNotFoundError, ValidationError, VersionNotFoundError
from .observability.runtime import RuntimeTelemetry

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables, heal stale pipeline runs. Shutdown: dispose engine."""
    try:
        from .database import engine, Base
        from .models import orm  # noqa: F401 — ensure ORM classes are registered
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # Run lightweight SQLite migrations independently.
            try:
                await conn.execute(
                    text("ALTER TABLE pipeline_runs ADD COLUMN steps_json TEXT")
                )
            except Exception:
                pass
            try:
                await conn.execute(
                    text("ALTER TABLE recommendations ADD COLUMN priority TEXT")
                )
            except Exception:
                pass
            try:
                # Backfill legacy null priorities first.
                await conn.execute(
                    text(
                        """
                        UPDATE recommendations
                        SET priority = CASE
                            WHEN lower(coalesce(recommendation_summary,'')) LIKE '%manual review%' THEN 'manual_review'
                            WHEN upgrade_recommended = 'Sufficient' THEN 'none'
                            ELSE 'manual_review'
                        END
                        WHERE priority IS NULL
                        """
                    )
                )

                # Rebuild table to enforce non-null + expanded priority check in SQLite.
                await conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS recommendations_new (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            library_id INTEGER NOT NULL,
                            priority TEXT NOT NULL CHECK (priority IN ('critical','high','moderate','low','none','manual_review')),
                            upgrade_recommended TEXT CHECK (upgrade_recommended IN ('Yes','No','Sufficient')),
                            recommendation_summary TEXT,
                            upgrade_pros TEXT,
                            upgrade_cons TEXT,
                            no_upgrade_pros TEXT,
                            no_upgrade_cons TEXT,
                            generated_at TEXT,
                            FOREIGN KEY(library_id) REFERENCES libraries(id)
                        )
                        """
                    )
                )
                await conn.execute(
                    text(
                        """
                        INSERT INTO recommendations_new (
                            id, library_id, priority, upgrade_recommended, recommendation_summary,
                            upgrade_pros, upgrade_cons, no_upgrade_pros, no_upgrade_cons, generated_at
                        )
                        SELECT
                            id,
                            library_id,
                            CASE
                                WHEN priority IN ('critical','high','moderate','low','none','manual_review') THEN priority
                                WHEN lower(coalesce(recommendation_summary,'')) LIKE '%manual review%' THEN 'manual_review'
                                WHEN upgrade_recommended = 'Sufficient' THEN 'none'
                                ELSE 'manual_review'
                            END,
                            upgrade_recommended,
                            recommendation_summary,
                            upgrade_pros,
                            upgrade_cons,
                            no_upgrade_pros,
                            no_upgrade_cons,
                            generated_at
                        FROM recommendations
                        """
                    )
                )
                await conn.execute(text("DROP TABLE recommendations"))
                await conn.execute(text("ALTER TABLE recommendations_new RENAME TO recommendations"))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_rec_lib ON recommendations(library_id)"))
            except Exception:
                pass
    except Exception as exc:
        # Table not yet created or startup race — continue boot
        pass
    try:
        from .database import db_context
        from .repositories.other_repos import PipelineRunRepository
        async with db_context() as db:
            repo = PipelineRunRepository(db)
            healed = await repo.heal_stale_runs(threshold_minutes=30)
            if healed:
                logger.warning("healed_stale_pipeline_runs", count=healed)
    except Exception as exc:
        logger.warning("lifespan_startup_warning", error=str(exc))
    app.state.runtime_telemetry = RuntimeTelemetry()
    logger.info("service_started", service=settings.service_name, version=settings.service_version)
    yield
    logger.info("service_stopped", service=settings.service_name)


app = FastAPI(
    title="Library Data Service",
    version=settings.service_version,
    description="Single source of truth for all library data. Only service with direct DB write access.",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(libraries.router)
app.include_router(version_history.router)
app.include_router(recommendations.router)
app.include_router(pipeline.router)
app.include_router(settings_router.router)
app.include_router(audit.router)
app.include_router(lifecycle.router)
app.include_router(llm_analytics.router)
app.include_router(cve.router)
app.include_router(teams.router)
app.include_router(sla.router)
app.include_router(versions_router.router)


@app.middleware("http")
async def runtime_telemetry_middleware(request: Request, call_next):
    start = perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        telemetry = getattr(request.app.state, "runtime_telemetry", None)
        if telemetry is not None:
            latency_ms = (perf_counter() - start) * 1000.0
            await telemetry.record(request.method, request.url.path, status_code, latency_ms)


# ── Exception handlers ────────────────────────────────────────────────────────
@app.exception_handler(LibraryNotFoundError)
async def library_not_found_handler(request: Request, exc: LibraryNotFoundError) -> JSONResponse:
    """Return a standardized 404 envelope when library lookup fails."""

    return JSONResponse(
        status_code=404,
        content={
            "success": False,
            "data": None,
            "error": {"code": "LIBRARY_NOT_FOUND", "message": str(exc), "detail": None},
            "meta": {"service": settings.service_name, "version": settings.service_version},
        },
    )


@app.exception_handler(VersionNotFoundError)
async def version_not_found_handler(request: Request, exc: VersionNotFoundError) -> JSONResponse:
    """Return a standardized 404 envelope when version history lookup fails."""

    return JSONResponse(
        status_code=404,
        content={
            "success": False,
            "data": None,
            "error": {"code": "VERSION_NOT_FOUND", "message": str(exc), "detail": None},
            "meta": {"service": settings.service_name, "version": settings.service_version},
        },
    )


@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
    """Return a standardized 400 envelope for domain validation failures."""

    return JSONResponse(
        status_code=400,
        content={
            "success": False,
            "data": None,
            "error": {"code": "VALIDATION_ERROR", "message": str(exc), "detail": None},
            "meta": {"service": settings.service_name, "version": settings.service_version},
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a standardized 500 envelope for unexpected unhandled exceptions."""

    logger.error(
        "unhandled_exception",
        exc_type=type(exc).__name__,
        exc_message=str(exc),
        path=str(request.url.path),
    )
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "data": None,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "detail": None,
            },
            "meta": {"service": settings.service_name, "version": settings.service_version},
        },
    )

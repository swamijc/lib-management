"""Scheduler Service — FastAPI application entry point."""
from __future__ import annotations
from contextlib import asynccontextmanager
from time import perf_counter

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import settings
from .routers import scheduler, health
from .routers.scheduler import get_service
from .services.scheduler_service import load_run_history_from_db
from .observability.runtime import RuntimeTelemetry

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(__import__("logging"), settings.log_level.upper(), 20)
    ),
)
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.runtime_telemetry = RuntimeTelemetry()
    svc = get_service()
    try:
        svc.start()
    except Exception as exc:
        logger.warning("scheduler_start_warning", error=str(exc))
    # Load persisted run history from library-data-service DB
    try:
        await load_run_history_from_db()
    except Exception as exc:
        logger.warning("load_run_history_warning", error=str(exc))
    logger.info("service_started", service=settings.service_name,
                version=settings.service_version)
    yield
    try:
        svc.shutdown()
    except Exception:
        pass
    logger.info("service_stopped", service=settings.service_name)


app = FastAPI(
    title="Scheduler Service",
    version=settings.service_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url=None,
)

app.include_router(scheduler.router)
app.include_router(health.router)


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


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", exc_type=type(exc).__name__, message=str(exc))
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "data": None,
            "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred", "detail": None},
            "meta": {"service": settings.service_name, "version": settings.service_version},
        },
    )

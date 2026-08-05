"""API Gateway — FastAPI application entry point."""
from __future__ import annotations
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from time import perf_counter

from .config import settings
from .auth.user_db import ensure_default_admin
from .routers import auth, business, api, health
from .observability.runtime import RuntimeTelemetry

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(__import__("logging"), settings.log_level.upper(), 20)
    ),
)
logger = structlog.get_logger(__name__)

limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit_default])


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        ensure_default_admin()
    except Exception as exc:
        logger.warning("default_admin_init_warning", error=str(exc))
    app.state.runtime_telemetry = RuntimeTelemetry()
    logger.info("service_started", service=settings.service_name,
                version=settings.service_version)
    yield
    logger.info("service_stopped", service=settings.service_name)


app = FastAPI(
    title="API Gateway",
    version=settings.service_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url=None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Allow any azurestaticapps.net subdomain plus localhost in dev
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://.*\.azurestaticapps\.net|http://localhost:\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(business.router)
app.include_router(api.router)
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
            "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred"},
            "meta": {"service": settings.service_name, "version": settings.service_version},
        },
    )

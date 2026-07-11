"""
Scraper Service — routers.

Endpoints:
  POST /api/v1/scrape           — scrape one library
  POST /api/v1/scrape/batch     — start async batch job
  GET  /api/v1/scrape/status/{job_id}  — poll batch job status
  GET  /api/v1/registries       — list supported registries
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..config import settings
from ..exceptions import (
    CircuitOpenError,
    PackageNotFoundError,
    ParseError,
    RegistryNotSupportedError,
)
from ..models.schemas import (
    BatchScrapeRequest,
    RegistryInfo,
    ScrapedVersion,
    ScrapeJobStatus,
    ScrapeRequest,
)
from ..services.scraper_service import ScraperService
from shared.models.base_schemas import ApiResponse, ResponseMeta

router = APIRouter(prefix="/api/v1", tags=["scraper"])
_svc = ScraperService()


def _meta() -> ResponseMeta:
    return ResponseMeta(service=settings.service_name, version=settings.service_version)


@router.post("/scrape", response_model=ApiResponse[ScrapedVersion])
async def scrape_one(req: ScrapeRequest) -> ApiResponse[ScrapedVersion]:
    """Scrape a single library and return its latest version."""
    try:
        result = await _svc.scrape_one(req)
    except RegistryNotSupportedError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PackageNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except CircuitOpenError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return ApiResponse.ok(data=result, meta=_meta())


@router.post("/scrape/batch", response_model=ApiResponse[dict])
async def scrape_batch(req: BatchScrapeRequest) -> ApiResponse[dict]:
    """Start an async batch scrape job. Returns job_id for polling."""
    job_id = await _svc.scrape_batch(req)
    return ApiResponse.ok(
        data={"job_id": job_id, "total": len(req.libraries), "status": "running"},
        meta=_meta(),
    )


@router.get("/scrape/status/{job_id}", response_model=ApiResponse[ScrapeJobStatus])
async def get_job_status(job_id: str) -> ApiResponse[ScrapeJobStatus]:
    """Poll the status of a batch scrape job."""
    job = await _svc.get_job_status(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return ApiResponse.ok(data=job, meta=_meta())


@router.get("/registries", response_model=ApiResponse[list[RegistryInfo]])
async def list_registries() -> ApiResponse[list[RegistryInfo]]:
    """List all registered scraper strategies."""
    return ApiResponse.ok(data=_svc.list_registries(), meta=_meta())

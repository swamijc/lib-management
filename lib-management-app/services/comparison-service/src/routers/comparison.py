"""
Comparison Service — routers.

Endpoints:
  POST /api/v1/compare          — compare one library
  POST /api/v1/compare/batch    — compare a list of libraries
  GET  /api/v1/comparisons      — placeholder (results stored in DB by scheduler)
  GET  /api/v1/comparisons/{library_id}  — latest result for one library (in-memory, from last batch)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..config import settings
from ..models.schemas import (
    BatchCompareRequest,
    BatchComparisonResult,
    CompareRequest,
    ComparisonResult,
)
from ..services.comparison_service import ComparisonService
from shared.models.base_schemas import ApiResponse, ResponseMeta

router = APIRouter(prefix="/api/v1", tags=["comparison"])
_svc = ComparisonService()

# In-memory cache of last batch result for GET /comparisons/{library_id}
_last_batch_results: dict[int, ComparisonResult] = {}


def _meta() -> ResponseMeta:
    return ResponseMeta(service=settings.service_name, version=settings.service_version)


@router.post("/compare", response_model=ApiResponse[ComparisonResult])
async def compare_one(req: CompareRequest) -> ApiResponse[ComparisonResult]:
    """Compare current vs latest version for a single library."""
    result = await _svc.compare_one(req)
    _last_batch_results[req.library_id] = result
    return ApiResponse.ok(data=result, meta=_meta())


@router.post("/compare/batch", response_model=ApiResponse[BatchComparisonResult])
async def compare_batch(req: BatchCompareRequest) -> ApiResponse[BatchComparisonResult]:
    """Compare a batch of libraries. Results cached in-memory for GET queries."""
    batch_result = await _svc.compare_batch(req)
    for r in batch_result.results:
        _last_batch_results[r.library_id] = r
    return ApiResponse.ok(data=batch_result, meta=_meta())


@router.get("/comparisons", response_model=ApiResponse[list[ComparisonResult]])
async def list_comparisons() -> ApiResponse[list[ComparisonResult]]:
    """Return all cached comparison results from the last batch run."""
    return ApiResponse.ok(data=list(_last_batch_results.values()), meta=_meta())


@router.get("/comparisons/{library_id}", response_model=ApiResponse[ComparisonResult])
async def get_comparison(library_id: int) -> ApiResponse[ComparisonResult]:
    """Return the latest cached comparison result for a specific library."""
    result = _last_batch_results.get(library_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No comparison result found for library_id={library_id}",
        )
    return ApiResponse.ok(data=result, meta=_meta())

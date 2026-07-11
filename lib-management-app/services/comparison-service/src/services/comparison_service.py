"""
Comparison Service — orchestrator.

Orchestrates:
  1. Accept CompareRequest(s)
  2. Run version_engine.compare_versions() for each library
  3. Return ComparisonResult(s) / BatchComparisonResult
"""
from __future__ import annotations

import structlog

from ..models.schemas import (
    BatchCompareRequest,
    BatchComparisonResult,
    CompareRequest,
    ComparisonResult,
    VersionStatus,
)
from .version_engine import compare_versions

logger = structlog.get_logger(__name__)


class ComparisonService:

    async def compare_one(self, req: CompareRequest) -> ComparisonResult:
        result = compare_versions(
            library_id=req.library_id,
            package=req.package,
            platform=req.platform,
            current_version=req.current_version,
            latest_version=req.latest_version,
            update_needed=req.update_needed,
            library_status=req.status,
        )
        logger.info(
            "comparison_done",
            library_id=req.library_id,
            package=req.package,
            status=result.version_status,
            new_version=result.new_version_released,
        )
        return result

    async def compare_batch(self, req: BatchCompareRequest) -> BatchComparisonResult:
        results: list[ComparisonResult] = []
        for lib in req.libraries:
            result = await self.compare_one(lib)
            results.append(result)

        newer = sum(1 for r in results if r.version_status == VersionStatus.NEWER)
        same = sum(1 for r in results if r.version_status == VersionStatus.SAME)
        older = sum(1 for r in results if r.version_status == VersionStatus.OLDER)
        unknown = sum(1 for r in results if r.version_status == VersionStatus.UNKNOWN)

        logger.info(
            "batch_comparison_done",
            total=len(results),
            newer=newer,
            same=same,
            older=older,
            unknown=unknown,
        )

        return BatchComparisonResult(
            total=len(results),
            newer_count=newer,
            same_count=same,
            older_count=older,
            unknown_count=unknown,
            results=results,
        )

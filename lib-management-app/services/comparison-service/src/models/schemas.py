"""
Comparison Service — Pydantic v2 DTOs.
"""
from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VersionStatus(str, Enum):
    NEWER = "newer"          # latest > current  → new release available
    SAME = "same"            # latest == current
    OLDER = "older"          # latest < current  (e.g. internal/custom version)
    UNKNOWN = "unknown"      # one or both versions unparseable


class CompareRequest(BaseModel):
    """Single-library comparison request."""
    library_id: int
    package: str
    platform: str
    current_version: str
    latest_version: str
    update_needed: str | None = None
    status: str | None = None

    model_config = {"json_schema_extra": {"example": {
        "library_id": 1,
        "package": "androidx.core:core-ktx",
        "platform": "Android",
        "current_version": "1.12.0",
        "latest_version": "1.15.0",
        "update_needed": "Mandatory",
    }}}


class BatchCompareRequest(BaseModel):
    """Batch comparison — list of libraries to compare."""
    libraries: list[CompareRequest] = Field(..., min_length=1, max_length=1000)


class ComparisonResult(BaseModel):
    """Result of a single version comparison."""
    library_id: int
    package: str
    platform: str
    current_version: str
    latest_version: str
    version_status: VersionStatus
    new_version_released: bool
    major_bump: bool = False      # major version increased
    minor_bump: bool = False      # minor version increased
    patch_bump: bool = False      # patch version increased
    needs_manual_review: bool = False  # unparseable version
    update_needed: str | None = None
    library_status: str | None = None
    compared_at: datetime = Field(default_factory=_utcnow)

    model_config = {"use_enum_values": True}


class BatchComparisonResult(BaseModel):
    """Result of a batch comparison run."""
    total: int
    newer_count: int        # libraries with newer versions available
    same_count: int
    older_count: int
    unknown_count: int
    results: list[ComparisonResult]
    compared_at: datetime = Field(default_factory=_utcnow)

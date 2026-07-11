"""
Scraper Service — Pydantic v2 DTOs.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


# ── Inbound request schemas ────────────────────────────────────────────────────

class ScrapeRequest(BaseModel):
    """Single-library scrape request."""
    package: str = Field(..., description="Package identifier (e.g. 'com.google.firebase:firebase-bom')")
    registry: str = Field(..., description="Registry key: maven|cocoapods|spm|github|custom")
    # For 'github' strategy: '<owner>/<repo>'
    # For 'custom' strategy: full URL supplied here
    custom_url: str | None = Field(default=None, description="URL override for custom registry")

    model_config = {"json_schema_extra": {"example": {"package": "androidx.core:core-ktx", "registry": "maven"}}}


class BatchScrapeRequest(BaseModel):
    """Batch scrape — list of individual requests."""
    libraries: list[ScrapeRequest] = Field(..., min_length=1, max_length=500)


# ── Outbound result schemas ────────────────────────────────────────────────────

class ScrapedVersion(BaseModel):
    """Parsed result from a registry scrape."""
    package: str
    registry: str
    latest_version: str
    release_notes: str | None = None
    release_date: str | None = None
    source_url: str | None = None
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
    from_cache: bool = False
    version_history: list[str] | None = None  # all versions parsed from release page (newest first)


class ScrapeError(BaseModel):
    """Per-library failure detail inside a batch result."""
    package: str
    registry: str
    error_code: str  # NOT_FOUND | CIRCUIT_OPEN | TIMEOUT | PARSE_ERROR | HTTP_ERROR
    message: str


class ScrapeJobStatus(BaseModel):
    """Status of an async batch scrape job."""
    job_id: str
    status: str  # pending | running | completed | failed
    total: int
    completed: int
    failed: int
    results: list[ScrapedVersion] = []
    errors: list[ScrapeError] = []
    started_at: datetime
    finished_at: datetime | None = None


class RegistryInfo(BaseModel):
    """Metadata for a registered scraper strategy."""
    registry_key: str
    display_name: str
    ecosystem: str
    base_url: str
    is_active: bool = True
    requires_auth: bool = False
    notes: str | None = None

"""
Scraper Service — core business logic.

Responsibilities:
  1. Check scrape_cache TTL before making a network call (T1 gap)
  2. Route to the correct ScraperStrategy via ScraperFactory
  3. Guard every external call with a per-registry CircuitBreaker
  4. Persist result to library-data-service via HTTP (optional — caller can also
     handle result directly for batch jobs)
  5. Manage in-process batch jobs (stored in-memory — ephemeral, by design)
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from ..circuit_breaker import CircuitBreaker, CircuitState
from ..config import settings
from ..exceptions import CircuitOpenError, RegistryNotSupportedError
from ..models.schemas import (
    BatchScrapeRequest,
    RegistryInfo,
    ScrapedVersion,
    ScrapeError,
    ScrapeJobStatus,
    ScrapeRequest,
)
from ..strategies.base import ScraperFactory

logger = structlog.get_logger(__name__)

# ── Static registry metadata (mirrors scraper_registry_config seed data) ───────
_REGISTRY_CATALOG: list[RegistryInfo] = [
    RegistryInfo(
        registry_key="maven",
        display_name="Maven Central",
        ecosystem="Android / Java",
        base_url="https://search.maven.org/solrsearch/select",
    ),
    RegistryInfo(
        registry_key="cocoapods",
        display_name="CocoaPods Trunk",
        ecosystem="iOS",
        base_url="https://trunk.cocoapods.org/api/v1/pods",
    ),
    RegistryInfo(
        registry_key="spm",
        display_name="Swift Package Index",
        ecosystem="iOS (SPM)",
        base_url="https://swiftpackageindex.com/api/packages",
    ),
    RegistryInfo(
        registry_key="github",
        display_name="GitHub Releases",
        ecosystem="Cross-platform (vendored/binary SDKs)",
        base_url="https://api.github.com/repos",
        notes="Optional: set GITHUB_TOKEN env var to avoid rate-limiting",
    ),
    RegistryInfo(
        registry_key="custom",
        display_name="Custom HTTP",
        ecosystem="Any (admin-configured URL per library)",
        base_url="(per-library admin config)",
    ),
]


class ScraperService:
    """
    Stateless per-request scraper orchestrator.
    Circuit breakers are class-level singletons so state persists across requests.
    In-memory job store is also class-level (resets on restart).
    """

    # ── Class-level state ────────────────────────────────────────────────────
    _circuit_breakers: dict[str, CircuitBreaker] = {}
    _jobs: dict[str, ScrapeJobStatus] = {}

    # ── Circuit breaker helpers ──────────────────────────────────────────────

    @classmethod
    def _get_breaker(cls, registry_key: str) -> CircuitBreaker:
        if registry_key not in cls._circuit_breakers:
            cls._circuit_breakers[registry_key] = CircuitBreaker(
                name=registry_key,
                failure_threshold=settings.circuit_breaker_failure_threshold,
                recovery_timeout=settings.circuit_breaker_recovery_timeout,
            )
        return cls._circuit_breakers[registry_key]

    # ── Cache freshness (T1 gap) ─────────────────────────────────────────────

    @staticmethod
    def _is_cache_fresh(scraped_at: datetime) -> bool:
        ttl = timedelta(hours=settings.scrape_cache_ttl_hours)
        return (datetime.now(timezone.utc) - scraped_at) < ttl

    # ── Public methods ───────────────────────────────────────────────────────

    async def scrape_one(
        self,
        req: ScrapeRequest,
        cached_result: ScrapedVersion | None = None,
    ) -> ScrapedVersion:
        """
        Scrape a single library.

        If `cached_result` is provided and still fresh, return it immediately.
        Otherwise call the strategy guarded by the circuit breaker.
        """
        if cached_result and self._is_cache_fresh(cached_result.scraped_at):
            logger.info("scrape_cache_hit", package=req.package, registry=req.registry)
            return ScrapedVersion(**cached_result.model_dump(), from_cache=True)

        breaker = self._get_breaker(req.registry)
        strategy = ScraperFactory.get(req.registry)

        kwargs: dict[str, Any] = {}
        if req.custom_url:
            kwargs["custom_url"] = req.custom_url
        if settings.github_token:
            kwargs["github_token"] = settings.github_token

        logger.info("scrape_start", package=req.package, registry=req.registry,
                    circuit=breaker.state.value)

        result: ScrapedVersion = await breaker.call(
            strategy.fetch, req.package, **kwargs
        )

        logger.info(
            "scrape_success",
            package=req.package,
            registry=req.registry,
            version=result.latest_version,
        )
        return result

    async def scrape_batch(self, req: BatchScrapeRequest) -> str:
        """
        Start an async batch scrape job.  Returns job_id immediately.
        Actual work runs as a background asyncio task.
        """
        job_id = str(uuid.uuid4())
        job = ScrapeJobStatus(
            job_id=job_id,
            status="running",
            total=len(req.libraries),
            completed=0,
            failed=0,
            started_at=datetime.now(timezone.utc),
        )
        self._jobs[job_id] = job
        asyncio.create_task(self._run_batch(job_id, req))
        return job_id

    async def get_job_status(self, job_id: str) -> ScrapeJobStatus | None:
        return self._jobs.get(job_id)

    def list_registries(self) -> list[RegistryInfo]:
        """Return registry metadata for all registered strategies."""
        available = set(ScraperFactory.available_keys())
        return [r for r in _REGISTRY_CATALOG if r.registry_key in available]

    # ── Batch execution (background task) ───────────────────────────────────

    async def _run_batch(self, job_id: str, req: BatchScrapeRequest) -> None:
        job = self._jobs[job_id]
        semaphore = asyncio.Semaphore(10)  # max 10 concurrent scrapes

        async def _scrape_with_semaphore(lib_req: ScrapeRequest) -> None:
            async with semaphore:
                try:
                    result = await self.scrape_one(lib_req)
                    job.results.append(result)
                    job.completed += 1
                except CircuitOpenError as exc:
                    job.errors.append(ScrapeError(
                        package=lib_req.package,
                        registry=lib_req.registry,
                        error_code="CIRCUIT_OPEN",
                        message=str(exc),
                    ))
                    job.failed += 1
                except RegistryNotSupportedError as exc:
                    job.errors.append(ScrapeError(
                        package=lib_req.package,
                        registry=lib_req.registry,
                        error_code="UNSUPPORTED_REGISTRY",
                        message=str(exc),
                    ))
                    job.failed += 1
                except Exception as exc:
                    error_code = type(exc).__name__.upper().replace("ERROR", "_ERROR")
                    job.errors.append(ScrapeError(
                        package=lib_req.package,
                        registry=lib_req.registry,
                        error_code=error_code,
                        message=str(exc),
                    ))
                    job.failed += 1

        await asyncio.gather(*[_scrape_with_semaphore(lib) for lib in req.libraries])

        job.status = "completed" if job.failed == 0 else "completed_with_errors"
        job.finished_at = datetime.now(timezone.utc)
        logger.info(
            "batch_scrape_finished",
            job_id=job_id,
            total=job.total,
            completed=job.completed,
            failed=job.failed,
        )

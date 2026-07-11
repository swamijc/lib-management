"""
Scheduler Service — pipeline step implementations.

Each step is a standalone async function.  The runner calls them in order,
short-circuiting on hard failure.  Steps receive/return a shared context dict
so data flows through without global state.

Architecture (Section 2.6):
  Step 1: fetch_libraries     → library-data-service GET /api/v1/libraries
  Step 2: batch_scrape        → scraper-service POST /api/v1/scrape/batch
                                  (polls until done, then writes latest_version back)
  Step 3: batch_compare       → comparison-service POST /api/v1/compare/batch
  Step 4: batch_recommend     → recommendation-service POST /api/v1/recommendations/generate/batch
  Step 5: notify              → notification-service POST /api/v1/notify/both
"""
from __future__ import annotations
import asyncio
import time
from datetime import datetime, timezone

import httpx
import structlog

from ..config import settings
from ..models.schemas import PipelineStatus, StepName, StepResult

logger = structlog.get_logger(__name__)

_HEADERS = {"X-Internal-Service-Key": settings.internal_service_key}
_TIMEOUT = settings.pipeline_step_timeout


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def step_fetch_libraries(ctx: dict) -> StepResult:
    """Fetch all library records from library-data-service."""
    started = _now()
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{settings.library_data_service_url}/api/v1/libraries",
                params={"limit": settings.pipeline_max_libraries},
                headers=_HEADERS,
            )
            resp.raise_for_status()
        body = resp.json()
        all_libraries = body.get("data", {}).get("libraries", [])
        libraries = [
            lib for lib in all_libraries
            if (lib.get("status") or "").strip().lower() != "inactive"
        ]
        ctx["libraries"] = libraries
        skipped_inactive = len(all_libraries) - len(libraries)
        logger.info(
            "pipeline_step_done",
            step="fetch_libraries",
            count=len(libraries),
            skipped_inactive=skipped_inactive,
        )
        return StepResult(
            step=StepName.FETCH_LIBRARIES,
            status=PipelineStatus.COMPLETED,
            message=(
                f"Fetched {len(libraries)} libraries"
                + (f"; skipped {skipped_inactive} inactive" if skipped_inactive else "")
            ),
            items_processed=len(libraries),
            duration_seconds=round(time.monotonic() - t0, 2),
            started_at=started,
            finished_at=_now(),
        )
    except Exception as exc:
        logger.error("pipeline_step_failed", step="fetch_libraries", error=str(exc))
        return StepResult(
            step=StepName.FETCH_LIBRARIES,
            status=PipelineStatus.FAILED,
            message=str(exc),
            duration_seconds=round(time.monotonic() - t0, 2),
            started_at=started,
            finished_at=_now(),
        )


async def step_batch_scrape(ctx: dict) -> StepResult:
    """Scrape latest versions for all libraries via scraper-service.

    Polls the batch job until completion, then writes each scraped latest_version
    back to library-data-service so that comparison/recommend steps use fresh data.
    """
    started = _now()
    t0 = time.monotonic()
    libraries: list[dict] = ctx.get("libraries", [])
    if not libraries:
        return StepResult(
            step=StepName.BATCH_SCRAPE,
            status=PipelineStatus.FAILED,
            message="No libraries to scrape (previous step produced no data)",
            started_at=started, finished_at=_now(),
        )

    # Build scrape requests — use registry from DB if available, else skip
    scrape_reqs = []
    lib_by_scraper_pkg: dict[str, dict] = {}   # keyed by what the scraper receives

    # Map verbose DB registry labels → scraper registry keys
    _REG_MAP: dict[str, str] = {
        "maven": "maven", "maven central": "maven",
        "maven/mvnrepository.com": "maven",
        "cocoapods": "cocoapods",
        "cocoapods/swift package manager": "cocoapods",
        "github": "github",
        "custom": "custom",
    }

    import re as _re

    def _github_owner_repo(repo_url: str) -> str | None:
        """Extract 'owner/repo' from a github.com URL."""
        m = _re.search(r"github\.com/([^/]+/[^/?\s#]+)", repo_url or "")
        return m.group(1).rstrip("/") if m else None

    for lib in libraries:
        raw_reg = (lib.get("registry") or lib.get("ecosystem") or "").strip()
        registry = _REG_MAP.get(raw_reg.lower())
        if not registry:
            continue  # spm / custom / unknown → no reliable scrape

        scraper_pkg = lib["package"]  # default: use pod name / maven coords
        if registry == "github":
            # GitHub scraper needs 'owner/repo' — derive from repo_url
            owner_repo = _github_owner_repo(lib.get("repo_url") or "")
            if not owner_repo:
                continue  # can't scrape without a valid GitHub URL
            scraper_pkg = owner_repo

        req: dict = {"package": scraper_pkg, "registry": registry}
        if registry == "custom":
            # For custom registry: use explicit custom_url field, fall back to repo_url
            custom_url = lib.get("custom_url") or lib.get("repo_url") or ""
            if not custom_url:
                continue  # no URL to scrape — skip
            req["custom_url"] = custom_url
        elif lib.get("custom_url"):
            req["custom_url"] = lib["custom_url"]
        scrape_reqs.append(req)
        lib_by_scraper_pkg[scraper_pkg] = lib

    if not scrape_reqs:
        return StepResult(
            step=StepName.BATCH_SCRAPE,
            status=PipelineStatus.COMPLETED,
            message="No libraries with registry info — scrape skipped",
            started_at=started, finished_at=_now(),
        )

    try:
        # ── 1. Start the async batch scrape job ─────────────────────────────
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{settings.scraper_service_url}/api/v1/scrape/batch",
                json={"libraries": scrape_reqs},
                headers=_HEADERS,
            )
            resp.raise_for_status()
        body = resp.json()
        job_id = body.get("data", {}).get("job_id")
        ctx["scrape_job_id"] = job_id
        logger.info("pipeline_step_scrape_started", job_id=job_id)

        # ── 2. Poll until the job finishes (max 120 s, 3 s intervals) ───────
        POLL_INTERVAL = 3.0
        MAX_WAIT = 120.0
        job_data: dict = {}
        deadline = time.monotonic() + MAX_WAIT
        while time.monotonic() < deadline:
            await asyncio.sleep(POLL_INTERVAL)
            async with httpx.AsyncClient(timeout=15.0) as pclient:
                try:
                    p = await pclient.get(
                        f"{settings.scraper_service_url}/api/v1/scrape/status/{job_id}",
                        headers=_HEADERS,
                    )
                    if p.status_code == 200:
                        job_data = p.json().get("data", {})
                        if job_data.get("status") in ("completed", "completed_with_errors"):
                            break
                except Exception:
                    pass  # transient error — keep polling

        results: list[dict] = job_data.get("results", [])
        logger.info("pipeline_step_scrape_polled", results=len(results))

        # ── 3. Write scraped latest_version back to library-data-service ────
        updated = 0
        skipped = 0
        from packaging.version import Version, InvalidVersion

        def _is_newer(scraped: str, current_db: str) -> bool:
            try:
                return Version(scraped) > Version(current_db)
            except InvalidVersion:
                return scraped.strip() != current_db.strip()

        async with httpx.AsyncClient(timeout=15.0) as wclient:
            for result in results:
                pkg = result.get("package", "")
                scraped_latest = result.get("latest_version", "")
                lib = lib_by_scraper_pkg.get(pkg)
                if not lib or not scraped_latest:
                    skipped += 1
                    continue

                lib_id = lib["id"]
                db_latest = lib.get("latest_version") or ""
                db_current = lib.get("current_version") or ""
                db_update_needed = (lib.get("update_needed") or "none").lower()

                # Only update if scraped version is strictly newer than what's in DB
                # (prevents downgrading when CocoaPods lags behind GitHub releases)
                if not _is_newer(scraped_latest, db_latest) and scraped_latest == db_latest:
                    skipped += 1
                    continue
                if db_latest and not _is_newer(scraped_latest, db_latest):
                    skipped += 1  # scraped is same or older — keep manual/master data
                    continue

                # Determine if update_needed should be upgraded
                # Only upgrade "none" → "Recommended" (never downgrade business decisions)
                new_update_needed: str | None = None
                if db_update_needed in ("none", "optional") and db_current and _is_newer(scraped_latest, db_current):
                    new_update_needed = "Recommended"

                patch: dict = {
                    "latest_version": scraped_latest,
                    "updated_by": "pipeline",  # required by LibraryUpdateRequest
                }
                if new_update_needed:
                    patch["update_needed"] = new_update_needed

                try:
                    wr = await wclient.put(
                        f"{settings.library_data_service_url}/api/v1/libraries/{lib_id}",
                        json=patch,
                        headers=_HEADERS,
                    )
                    if wr.status_code == 200:
                        # Update context so comparison step uses fresh data
                        lib["latest_version"] = scraped_latest
                        if new_update_needed:
                            lib["update_needed"] = new_update_needed
                        updated += 1

                        # ── Save version_history entries for HTML-scraped SDKs ──
                        version_history: list[str] = result.get("version_history") or []
                        if version_history:
                            for ver in version_history:
                                try:
                                    await wclient.post(
                                        f"{settings.library_data_service_url}/api/v1/version-history",
                                        json={
                                            "library_id": lib_id,
                                            "version_number": ver,
                                            "record_type": "historical",
                                            "source": "html_scrape",
                                            "notes": None,
                                        },
                                        headers=_HEADERS,
                                    )
                                except Exception:
                                    pass  # non-critical — continue
                    else:
                        skipped += 1
                except Exception as we:
                    logger.warning("scrape_writeback_failed", lib_id=lib_id, error=str(we)[:80])
                    skipped += 1

        logger.info("pipeline_step_done", step="batch_scrape",
                    job_id=job_id, scraped=len(results), updated=updated, skipped=skipped)
        return StepResult(
            step=StepName.BATCH_SCRAPE,
            status=PipelineStatus.COMPLETED,
            message=f"Scraped {len(results)} libs; {updated} latest_version updated in DB",
            items_processed=len(scrape_reqs),
            duration_seconds=round(time.monotonic() - t0, 2),
            started_at=started,
            finished_at=_now(),
        )
    except Exception as exc:
        logger.error("pipeline_step_failed", step="batch_scrape", error=str(exc))
        return StepResult(
            step=StepName.BATCH_SCRAPE,
            status=PipelineStatus.FAILED,
            message=str(exc),
            duration_seconds=round(time.monotonic() - t0, 2),
            started_at=started,
            finished_at=_now(),
        )


async def step_fetch_version_history(ctx: dict) -> StepResult:
    """
    Fetch full version history from Maven Central (Android) / CocoaPods (iOS)
    for all libraries in parallel.  Stores results in library-data-service.
    Non-critical: failures are logged but don't block the pipeline.
    """
    import asyncio
    started = _now()
    t0 = time.monotonic()
    libraries: list[dict] = ctx.get("libraries", [])

    # Only process libraries with Maven coordinates (Android) or CocoaPods (iOS)
    eligible = [
        lib for lib in libraries
        if (
            # Maven: package has group:artifact format
            ":" in lib.get("package", "")
            # CocoaPods: iOS platform with cocoapods registry
            or "cocoapods" in (lib.get("registry") or "").lower()
        )
    ]

    if not eligible:
        return StepResult(
            step=StepName.FETCH_VERSION_HISTORY,
            status=PipelineStatus.COMPLETED,
            message="No Maven/CocoaPods libraries — version history fetch skipped",
            items_processed=0,
            duration_seconds=round(time.monotonic() - t0, 2),
            started_at=started,
            finished_at=_now(),
        )

    ok = 0; fail = 0
    semaphore = asyncio.Semaphore(5)  # max 5 concurrent fetches

    async def _fetch_one(lib: dict) -> None:
        nonlocal ok, fail
        async with semaphore:
            try:
                async with httpx.AsyncClient(timeout=25.0) as client:
                    resp = await client.post(
                        f"{settings.library_data_service_url}/api/v1/libraries/{lib['id']}/fetch-versions",
                        headers=_HEADERS,
                    )
                    if resp.status_code in (200, 201):
                        ok += 1
                    else:
                        fail += 1
                        logger.warning(
                            "version_history_fetch_failed",
                            library_id=lib["id"],
                            package=lib.get("package"),
                            status=resp.status_code,
                        )
            except Exception as exc:
                fail += 1
                logger.warning(
                    "version_history_fetch_error",
                    library_id=lib["id"],
                    package=lib.get("package"),
                    error=str(exc)[:100],
                )

    await asyncio.gather(*[_fetch_one(lib) for lib in eligible])

    # ── Build release_notes_map for recommendation step ─────────────────────
    # Aggregate release notes across the full version window current -> latest,
    # so priority classification considers intermediate releases as well.
    release_notes_map: dict[int, str] = {}
    release_window_summary_map: dict[int, str] = {}

    def _window_release_notes(current_ver: str, latest_ver: str, versions: list[dict]) -> tuple[str, str]:
        """
        Return (merged release notes for versions in (current, latest], window summary).
        Falls back to latest release notes when semantic comparison is not possible.
        """
        from packaging.version import Version, InvalidVersion

        curr = (current_ver or "").strip()
        latest = (latest_ver or "").strip()

        if not versions:
            return "", ""

        latest_row = next((v for v in versions if v.get("is_latest")), None)
        latest_notes = (latest_row or {}).get("release_notes") or ""

        def _fmt_ver(v: str) -> str:
            vv = (v or "").strip()
            if not vv:
                return "?"
            return vv if vv.lower().startswith("v") else f"v{vv}"

        try:
            curr_v = Version(curr)
            latest_v = Version(latest)
            if latest_v <= curr_v:
                return latest_notes, ""

            in_window: list[str] = []
            for row in versions:
                vv = (row.get("version") or "").strip()
                if not vv:
                    continue
                try:
                    v_obj = Version(vv)
                except InvalidVersion:
                    continue
                if curr_v < v_obj <= latest_v:
                    in_window.append(str(v_obj))

            intermediate_count = max(0, len(set(in_window)) - 1)
            window_summary = (
                f"Version window: {_fmt_ver(curr)} -> {_fmt_ver(latest)} "
                f"({intermediate_count} intermediate releases considered)"
            )

            picked: list[tuple[str, str]] = []
            for row in versions:
                vv = (row.get("version") or "").strip()
                rn = (row.get("release_notes") or "").strip()
                if not vv or not rn:
                    continue
                try:
                    v_obj = Version(vv)
                except InvalidVersion:
                    continue
                if curr_v < v_obj <= latest_v:
                    picked.append((str(v_obj), rn))

            if not picked:
                return latest_notes, window_summary

            # Order by parsed version for deterministic concatenation.
            picked.sort(key=lambda x: Version(x[0]))

            merged_parts: list[str] = []
            seen: set[str] = set()
            for _, note in picked:
                compact = " ".join(note.split())
                if compact and compact not in seen:
                    merged_parts.append(compact)
                    seen.add(compact)

            merged = "\n\n".join(merged_parts)
            return merged or latest_notes, window_summary
        except Exception:
            # Non-semver versions are handled by manual-review downstream.
            return latest_notes, ""

    async def _get_notes(lib: dict) -> None:
        try:
            async with httpx.AsyncClient(timeout=10.0) as nc:
                r = await nc.get(
                    f"{settings.library_data_service_url}/api/v1/libraries/{lib['id']}/versions",
                    headers=_HEADERS,
                )
                if r.status_code == 200:
                    versions = r.json().get("data", {}).get("versions", [])
                    merged_notes, window_summary = _window_release_notes(
                        lib.get("current_version") or "",
                        lib.get("latest_version") or "",
                        versions,
                    )
                    if merged_notes:
                        release_notes_map[lib["id"]] = merged_notes
                    if window_summary:
                        release_window_summary_map[lib["id"]] = window_summary
        except Exception:
            pass  # release notes are optional — don't block pipeline

    notes_semaphore = asyncio.Semaphore(10)
    async def _get_notes_throttled(lib: dict) -> None:
        async with notes_semaphore:
            await _get_notes(lib)

    await asyncio.gather(*[_get_notes_throttled(lib) for lib in eligible])
    ctx["release_notes_map"] = release_notes_map
    ctx["release_window_summary_map"] = release_window_summary_map
    logger.info("release_notes_collected", count=len(release_notes_map))

    total = len(eligible)
    status = PipelineStatus.COMPLETED if fail == 0 else (
        PipelineStatus.COMPLETED if ok > 0 else PipelineStatus.FAILED
    )
    logger.info("pipeline_step_done", step="fetch_version_history",
                total=total, ok=ok, fail=fail)
    return StepResult(
        step=StepName.FETCH_VERSION_HISTORY,
        status=status,
        message=f"Version history fetched for {ok}/{total} libraries"
                + (f"; {fail} failed (non-critical)" if fail else ""),
        items_processed=ok,
        duration_seconds=round(time.monotonic() - t0, 2),
        started_at=started,
        finished_at=_now(),
    )


async def step_batch_compare(ctx: dict) -> StepResult:
    """Compare current vs latest versions via comparison-service."""
    started = _now()
    t0 = time.monotonic()
    libraries: list[dict] = ctx.get("libraries", [])
    if not libraries:
        return StepResult(
            step=StepName.BATCH_COMPARE,
            status=PipelineStatus.FAILED,
            message="No libraries to compare",
            started_at=started, finished_at=_now(),
        )

    compare_reqs = [
        {
            "library_id": lib["id"],
            "package": lib["package"] or "",
            "platform": lib.get("platform") or "",
            "current_version": lib.get("current_version") or "",
            "latest_version": lib.get("latest_version") or "",
            "update_needed": lib.get("update_needed"),
            "status": lib.get("status"),
        }
        for lib in libraries
        if lib.get("current_version") and lib.get("latest_version")
    ]

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{settings.comparison_service_url}/api/v1/compare/batch",
                json={"libraries": compare_reqs},
                headers=_HEADERS,
            )
            resp.raise_for_status()
        body = resp.json()
        comparison_results = body.get("data", {}).get("results", [])
        ctx["comparison_results"] = comparison_results
        newer_count = body.get("data", {}).get("newer_count", 0)
        logger.info("pipeline_step_done", step="batch_compare",
                    total=len(comparison_results), newer=newer_count)
        return StepResult(
            step=StepName.BATCH_COMPARE,
            status=PipelineStatus.COMPLETED,
            message=f"Compared {len(comparison_results)} libraries; {newer_count} with newer versions",
            items_processed=len(comparison_results),
            duration_seconds=round(time.monotonic() - t0, 2),
            started_at=started,
            finished_at=_now(),
        )
    except Exception as exc:
        logger.error("pipeline_step_failed", step="batch_compare", error=str(exc))
        return StepResult(
            step=StepName.BATCH_COMPARE,
            status=PipelineStatus.FAILED,
            message=str(exc),
            duration_seconds=round(time.monotonic() - t0, 2),
            started_at=started,
            finished_at=_now(),
        )


async def step_batch_recommend(ctx: dict) -> StepResult:
    """Generate recommendations via recommendation-service."""
    started = _now()
    t0 = time.monotonic()
    libraries: list[dict] = ctx.get("libraries", [])
    comparison_map: dict[int, dict] = {
        c["library_id"]: c for c in ctx.get("comparison_results", [])
    }

    if not libraries:
        return StepResult(
            step=StepName.BATCH_RECOMMEND,
            status=PipelineStatus.FAILED,
            message="No libraries for recommendation",
            started_at=started, finished_at=_now(),
        )

    rec_reqs = []
    for lib in libraries:
        lib_id = lib["id"]
        cmp = comparison_map.get(lib_id, {})
        # Get release notes from version history stored in ctx
        release_notes = ctx.get("release_notes_map", {}).get(lib_id, "")
        version_window_summary = ctx.get("release_window_summary_map", {}).get(lib_id, "")
        dep_notes = (lib.get("deprecation_notes") or "").strip()
        comments = (lib.get("comments") or "").strip()
        extra_context = " | ".join([p for p in [dep_notes, comments] if p])
        rec_reqs.append({
            "library_id":           lib_id,
            "package":              lib["package"] or "",
            "platform":             lib.get("platform") or "",
            "current_version":      lib.get("current_version") or "",
            "latest_version":       lib.get("latest_version") or "",
            "update_needed":        lib.get("update_needed"),
            "library_status":       lib.get("status"),
            "new_version_released": cmp.get("new_version_released", False),
            "version_status":       cmp.get("version_status"),
            "needs_manual_review":  cmp.get("needs_manual_review", False),
            "release_notes":        release_notes,
            "deprecation_notes":    extra_context,
            "version_window_summary": version_window_summary,
        })

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{settings.recommendation_service_url}/api/v1/recommendations/generate/batch",
                json={"libraries": rec_reqs},
                headers=_HEADERS,
            )
            resp.raise_for_status()
        body = resp.json()
        rec_results = body.get("data", {}).get("results", [])
        ctx["recommendation_results"] = rec_results
        yes_count = body.get("data", {}).get("yes_count", 0)

        # ── Write new 4-tier priority back to libraries DB ──────────────────
        # Primary source is recommendation.priority; summary parsing is fallback.
        import re as _re
        _PRIO_PATTERN = _re.compile(r'^\[(CRITICAL|HIGH|MODERATE|LOW)\]')
        _PRIO_MAP = {"CRITICAL": "critical", "HIGH": "high",
                     "MODERATE": "moderate", "LOW": "low"}
        _VALID_PRIORITY = {"critical", "high", "moderate", "low", "none", "manual_review"}
        priority_updated = 0
        async with httpx.AsyncClient(timeout=15.0) as wclient:
            for rec in rec_results:
                lib_id = rec.get("library_id")
                summary = rec.get("recommendation_summary", "") or ""
                decision = (rec.get("upgrade_recommended") or "").lower()
                direct_priority = (rec.get("priority") or "").strip().lower()
                lib = next((l for l in libraries if l["id"] == lib_id), None)
                if not lib_id or not lib:
                    continue

                if direct_priority in _VALID_PRIORITY:
                    new_priority = direct_priority
                elif "deprecated" in summary.lower():
                    # Deprecated library → critical priority
                    new_priority = "critical"
                elif decision == "sufficient" or "up-to-date" in summary.lower() or "no upgrade" in summary.lower():
                    # Up-to-date / no upgrade needed → none
                    new_priority = "none"
                else:
                    m = _PRIO_PATTERN.match(summary)
                    if m:
                        # Backward-compatible fallback for older recommendation payloads
                        new_priority = _PRIO_MAP[m.group(1)]
                    else:
                        continue  # manual review or unknown — don't change

                if new_priority == "manual_review":
                    # Libraries table uses update_needed buckets; map explicit manual review there.
                    new_priority = "moderate"

                # Only update if different from current value
                if (lib.get("update_needed") or "").lower() != new_priority:
                    wr = await wclient.put(
                        f"{settings.library_data_service_url}/api/v1/libraries/{lib_id}",
                        json={"update_needed": new_priority, "updated_by": "pipeline"},
                        headers=_HEADERS,
                    )
                    if wr.status_code == 200:
                        lib["update_needed"] = new_priority  # update ctx
                        priority_updated += 1

        logger.info("pipeline_step_done", step="batch_recommend",
                    total=len(rec_results), upgrade_yes=yes_count,
                    priority_updated=priority_updated)
        return StepResult(
            step=StepName.BATCH_RECOMMEND,
            status=PipelineStatus.COMPLETED,
            message=f"Generated {len(rec_results)} recommendations; {yes_count} upgrades; {priority_updated} priorities updated",
            items_processed=len(rec_results),
            duration_seconds=round(time.monotonic() - t0, 2),
            started_at=started,
            finished_at=_now(),
        )
    except Exception as exc:
        logger.error("pipeline_step_failed", step="batch_recommend", error=str(exc))
        return StepResult(
            step=StepName.BATCH_RECOMMEND,
            status=PipelineStatus.FAILED,
            message=str(exc),
            duration_seconds=round(time.monotonic() - t0, 2),
            started_at=started,
            finished_at=_now(),
        )


async def step_check_deadlines(ctx: dict) -> StepResult:
    """
    Deadline enforcement step.
    Calls library-data-service POST /api/v1/sla/enforce-deadlines which:
      - Escalates overdue libraries (deadline passed, not completed) to 'mandatory'
      - Pre-warns libraries within 7 days of deadline to 'mandatory'
      - Writes full audit log entries for every escalation
      - Stores overdue/approaching lists in ctx for the notify step
    """
    started = _now()
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{settings.library_data_service_url}/api/v1/sla/enforce-deadlines",
                headers=_HEADERS,
            )
            resp.raise_for_status()

        result = resp.json().get("data", {})
        overdue_escalated = result.get("overdue_escalated", 0)
        warning_escalated = result.get("warning_escalated", 0)
        already_done      = result.get("already_done", 0)

        ctx["deadline_overdue_count"]  = overdue_escalated
        ctx["deadline_warning_count"]  = warning_escalated

        # Fetch overdue and approaching-7d lists so the notify step can include them
        async with httpx.AsyncClient(timeout=10.0) as nc:
            or_resp = await nc.get(
                f"{settings.library_data_service_url}/api/v1/sla/overdue",
                headers=_HEADERS,
            )
            ap_resp = await nc.get(
                f"{settings.library_data_service_url}/api/v1/sla/approaching?days_ahead=7",
                headers=_HEADERS,
            )
        ctx["overdue_libs"]     = or_resp.json().get("data", []) if or_resp.status_code == 200 else []
        ctx["approaching_libs"] = ap_resp.json().get("data", []) if ap_resp.status_code == 200 else []

        total_affected = overdue_escalated + warning_escalated
        msg = (
            f"Deadline enforcement: {overdue_escalated} overdue escalated to mandatory, "
            f"{warning_escalated} approaching (≤7d) pre-warned, {already_done} already done"
        )
        logger.info("pipeline_step_done", step="check_deadlines",
                    overdue=overdue_escalated, warning=warning_escalated)
        return StepResult(
            step=StepName.CHECK_DEADLINES,
            status=PipelineStatus.COMPLETED,
            message=msg,
            items_processed=total_affected,
            duration_seconds=round(time.monotonic() - t0, 2),
            started_at=started,
            finished_at=_now(),
        )
    except Exception as exc:
        logger.error("pipeline_step_failed", step="check_deadlines", error=str(exc))
        return StepResult(
            step=StepName.CHECK_DEADLINES,
            status=PipelineStatus.FAILED,
            message=str(exc)[:200],
            duration_seconds=round(time.monotonic() - t0, 2),
            started_at=started,
            finished_at=_now(),
        )


async def step_notify(ctx: dict) -> StepResult:
    """Send notifications via notification-service."""
    started = _now()
    t0 = time.monotonic()
    libraries: list[dict] = ctx.get("libraries", [])
    rec_map: dict[int, dict] = {
        r["library_id"]: r for r in ctx.get("recommendation_results", [])
    }

    if not libraries:
        return StepResult(
            step=StepName.NOTIFY,
            status=PipelineStatus.FAILED,
            message="No library data to send in notification",
            started_at=started, finished_at=_now(),
        )

    notify_libs = [
        {
            "library_id": lib["id"],
            "package": lib["package"] or "",
            "platform": lib.get("platform") or "",
            "current_version": lib.get("current_version") or "",
            "latest_version": lib.get("latest_version") or "",
            "update_needed": lib.get("update_needed"),
            "library_status": lib.get("status"),
            "upgrade_recommended": rec_map.get(lib["id"], {}).get("upgrade_recommended"),
            "recommendation_summary": rec_map.get(lib["id"], {}).get("recommendation_summary"),
            "alert_priority": lib.get("alert_priority"),
            "deadline_date": lib.get("deadline_date"),
            "deadline_notes": lib.get("deadline_notes"),
        }
        for lib in libraries
    ]

    try:
        # ── Fetch notification config from library-data-service DB ────────────
        # Allows users to configure credentials via Settings UI without .env edits
        smtp_override = None
        teams_webhook = None
        email_recipients: list[str] = []
        email_enabled = False
        teams_enabled = False

        try:
            async with httpx.AsyncClient(timeout=10.0) as cfg_client:
                cfg_resp = await cfg_client.get(
                    f"{settings.library_data_service_url}/api/v1/settings/app",
                    headers=_HEADERS,
                )
                if cfg_resp.status_code == 200:
                    cfg_data = {s["key"]: s["value"] for s in cfg_resp.json().get("data", [])}
                    email_enabled = cfg_data.get("email_enabled", "0") == "1"
                    teams_enabled = cfg_data.get("teams_enabled", "0") == "1"

                    if email_enabled:
                        smtp_user = cfg_data.get("smtp_username", "")
                        smtp_pass = cfg_data.get("smtp_password", "")
                        if smtp_user and smtp_pass:
                            smtp_override = {
                                "host":         cfg_data.get("smtp_host", "smtp.office365.com"),
                                "port":         int(cfg_data.get("smtp_port", "587") or "587"),
                                "username":     smtp_user,
                                "password":     smtp_pass,
                                "from_address": cfg_data.get("smtp_from_address", smtp_user),
                                "use_tls":      cfg_data.get("smtp_use_tls", "1") == "1",
                            }
                        import json as _json
                        try:
                            email_recipients = _json.loads(cfg_data.get("email_recipients", "[]"))
                        except Exception:
                            email_recipients = []

                    if teams_enabled:
                        teams_webhook = cfg_data.get("teams_webhook_url", "") or None
        except Exception as cfg_exc:
            logger.warning("notify_config_fetch_failed", error=str(cfg_exc))

        # ── If no channel configured, skip gracefully with clear message ──────
        if not email_enabled and not teams_enabled:
            logger.info("notify_skipped_no_channels")
            return StepResult(
                step=StepName.NOTIFY,
                status=PipelineStatus.COMPLETED,
                message="No notification channels enabled — configure in ⚙️ Settings → 🔔 Notifications",
                items_processed=len(notify_libs),
                duration_seconds=round(time.monotonic() - t0, 2),
                started_at=started,
                finished_at=_now(),
            )

        # ── Build payload with DB credentials ─────────────────────────────────
        notify_payload: dict = {"libraries": notify_libs, "force_send": False}
        if smtp_override:
            notify_payload["smtp_override"] = smtp_override
        if email_recipients:
            notify_payload["recipients"] = email_recipients
        if teams_webhook:
            notify_payload["teams_webhook_override"] = teams_webhook

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{settings.notification_service_url}/api/v1/notify/both",
                json=notify_payload,
                headers=_HEADERS,
            )
            resp.raise_for_status()
        body = resp.json()
        skipped = body.get("data", {}).get("skipped_by_dedup", False)
        channels = []
        if email_enabled: channels.append("email")
        if teams_enabled: channels.append("Teams")
        ch_str = " + ".join(channels) if channels else "none"
        msg = (f"Duplicate — skipped ({ch_str})" if skipped
               else f"Sent via {ch_str}")
        logger.info("pipeline_step_done", step="notify", skipped_by_dedup=skipped, channels=ch_str)
        return StepResult(
            step=StepName.NOTIFY,
            status=PipelineStatus.COMPLETED,
            message=msg,
            items_processed=len(notify_libs),
            duration_seconds=round(time.monotonic() - t0, 2),
            started_at=started,
            finished_at=_now(),
        )
    except Exception as exc:
        logger.error("pipeline_step_failed", step="notify", error=str(exc))
        return StepResult(
            step=StepName.NOTIFY,
            status=PipelineStatus.FAILED,
            message=str(exc),
            duration_seconds=round(time.monotonic() - t0, 2),
            started_at=started,
            finished_at=_now(),
        )

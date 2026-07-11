"""Router: /api/v1/sla — SLA tracking, overdue detection, release notes."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models.orm import Library, UpgradeLifecycle
from shared.models.base_schemas import ApiResponse, ResponseMeta

router = APIRouter(prefix="/api/v1/sla", tags=["sla"])


def _meta() -> ResponseMeta:
    return ResponseMeta(service=settings.service_name, version=settings.service_version)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _days_overdue(deadline: str) -> int:
    try:
        dl = datetime.strptime(deadline[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - dl).days)
    except Exception:
        return 0


def _days_until(deadline: str) -> int:
    try:
        dl = datetime.strptime(deadline[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return (dl - datetime.now(timezone.utc)).days
    except Exception:
        return 999


def _normalize_update_needed(value: str | None) -> str:
    return (value or "").strip().lower()


def _priority_counts(libs: list[Library]) -> dict:
    return {
        "critical": sum(1 for l in libs if _normalize_update_needed(l.update_needed) == "critical"),
        "high": sum(1 for l in libs if _normalize_update_needed(l.update_needed) == "high"),
        "moderate": sum(1 for l in libs if _normalize_update_needed(l.update_needed) == "moderate"),
        "low": sum(1 for l in libs if _normalize_update_needed(l.update_needed) == "low"),
        "mandatory": sum(1 for l in libs if _normalize_update_needed(l.update_needed) == "mandatory"),
        "up_to_date": sum(1 for l in libs if _normalize_update_needed(l.update_needed) in ("none", "optional", "")),
    }


def _risk_score(counts: dict, total: int) -> int:
    if total <= 0:
        return 0
    weighted = (
        (counts.get("critical", 0) + counts.get("mandatory", 0)) * 4
        + counts.get("high", 0) * 3
        + counts.get("moderate", 0) * 2
        + counts.get("low", 0)
    )
    return round((weighted / (total * 4)) * 100)


def _is_high_risk(update_needed: str | None) -> bool:
    return _normalize_update_needed(update_needed) in ("mandatory", "critical", "high")


@router.get("/overdue", response_model=ApiResponse[list[dict]])
async def get_overdue(
    platform: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[dict]]:
    """
    Libraries that have passed their deadline_date without being upgraded.
    Excludes libraries already at latest version (update_needed='none').
    """
    today = _today()
    stmt = (
        select(Library)
        .where(Library.deadline_date.isnot(None))
        .where(Library.deadline_date < today)
        .where(Library.update_needed != "none")
        .where(Library.update_needed != "optional")
        .order_by(Library.deadline_date)
    )
    if platform:
        stmt = stmt.where(Library.platform == platform)

    libs = (await db.execute(stmt)).scalars().all()
    data = [
        {
            "library_id":    l.id,
            "package":       l.package,
            "sdk_name":      l.sdk_name,
            "platform":      l.platform,
            "current_version": l.current_version,
            "latest_version":  l.latest_version,
            "update_needed":   l.update_needed,
            "status":          l.status,
            "priority":        l.priority,
            "deadline_date":   l.deadline_date,
            "deadline_notes":  l.deadline_notes,
            "days_overdue":    _days_overdue(l.deadline_date or ""),
            "alert_priority":  l.alert_priority,
        }
        for l in libs
    ]
    return ApiResponse.ok(data=data, meta=_meta())


@router.post("/enforce-deadlines", response_model=ApiResponse[dict])
async def enforce_deadlines(db: AsyncSession = Depends(get_db)) -> ApiResponse[dict]:
    """
    Deadline enforcement engine — called by the scheduler pipeline on every run.

    Business rules (all enforced in backend, persisted to DB):
      - deadline_date < today  AND lifecycle not Completed → escalate update_needed to 'mandatory'
      - deadline_date within 7 days AND not yet mandatory → pre-warn (escalate to 'mandatory')
      - lifecycle status = Completed → exempt, skip enforcement
      - update_needed = 'none'/'optional' → exempt (upgrade already done)

    Every escalation is written to library_update_log for full audit trail.
    """
    from ..models.orm import LibraryUpdateLog

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    warn_cutoff = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d")
    _now_iso = datetime.now(timezone.utc).isoformat()

    # All libraries that have a deadline set
    all_deadline_libs = (await db.execute(
        select(Library).where(Library.deadline_date.isnot(None))
    )).scalars().all()

    # Libraries whose lifecycle is Completed — exempt from escalation
    completed_lib_ids: set[int] = set(
        row[0] for row in (await db.execute(
            select(UpgradeLifecycle.library_id)
            .where(UpgradeLifecycle.status == "Completed")
        )).all()
    )

    overdue_escalated = 0
    warning_escalated = 0
    already_done      = 0

    for lib in all_deadline_libs:
        if not lib.deadline_date:
            continue

        # Lifecycle completed — upgrade done, honour it
        if lib.id in completed_lib_ids:
            already_done += 1
            continue

        # update_needed is already 'none'/'optional' — version is current
        un = (lib.update_needed or "").strip().lower()
        if un in ("none", "optional"):
            already_done += 1
            continue

        dl = lib.deadline_date[:10]
        is_overdue = dl < today
        is_warning = not is_overdue and today <= dl <= warn_cutoff

        if is_overdue and un != "mandatory":
            old_val = lib.update_needed
            lib.update_needed = "mandatory"
            lib.updated_at = _now_iso
            db.add(LibraryUpdateLog(
                library_id=lib.id,
                updated_by="deadline-enforcer",
                update_type="deadline_escalation",
                field_changed="update_needed",
                old_value=old_val,
                new_value="mandatory",
                reason=f"Deadline {dl} passed without upgrade — auto-escalated to mandatory",
                updated_at=_now_iso,
            ))
            overdue_escalated += 1

        elif is_warning and un not in ("mandatory", "critical"):
            old_val = lib.update_needed
            lib.update_needed = "mandatory"
            lib.updated_at = _now_iso
            db.add(LibraryUpdateLog(
                library_id=lib.id,
                updated_by="deadline-enforcer",
                update_type="deadline_warning",
                field_changed="update_needed",
                old_value=old_val,
                new_value="mandatory",
                reason=f"Deadline {dl} within 7 days without upgrade — pre-warned to mandatory",
                updated_at=_now_iso,
            ))
            warning_escalated += 1

    await db.commit()

    return ApiResponse.ok(
        data={
            "overdue_escalated":   overdue_escalated,
            "warning_escalated":   warning_escalated,
            "already_done":        already_done,
            "total_deadline_libs": len(all_deadline_libs),
            "checked_at":          today,
        },
        meta=_meta(),
    )


@router.get("/approaching", response_model=ApiResponse[list[dict]])
async def get_approaching(
    days_ahead: int = Query(default=30, ge=1, le=180),
    platform: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[dict]]:
    """
    Libraries with deadline_date within the next N days.
    Excludes already-completed upgrades.
    """
    today = _today()
    cutoff = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    stmt = (
        select(Library)
        .where(Library.deadline_date.isnot(None))
        .where(Library.deadline_date >= today)
        .where(Library.deadline_date <= cutoff)
        .where(Library.update_needed != "none")
        .order_by(Library.deadline_date)
    )
    if platform:
        stmt = stmt.where(Library.platform == platform)

    libs = (await db.execute(stmt)).scalars().all()
    data = [
        {
            "library_id":   l.id,
            "package":      l.package,
            "sdk_name":     l.sdk_name,
            "platform":     l.platform,
            "current_version": l.current_version,
            "latest_version":  l.latest_version,
            "update_needed":   l.update_needed,
            "deadline_date":   l.deadline_date,
            "deadline_notes":  l.deadline_notes,
            "days_until":      _days_until(l.deadline_date or ""),
        }
        for l in libs
    ]
    return ApiResponse.ok(data=data, meta=_meta())


@router.get("/summary", response_model=ApiResponse[dict])
async def get_sla_summary(db: AsyncSession = Depends(get_db)) -> ApiResponse[dict]:
    """Dashboard SLA health summary."""
    today = _today()
    all_libs = (await db.execute(select(Library))).scalars().all()
    with_deadline = [l for l in all_libs if l.deadline_date]
    overdue     = [l for l in with_deadline if l.deadline_date < today and (l.update_needed or "").lower() not in ("none","optional")]
    within_7    = [l for l in with_deadline if today <= (l.deadline_date or "") <= (datetime.now(timezone.utc)+timedelta(days=7)).strftime("%Y-%m-%d") and (l.update_needed or "").lower() not in ("none","optional")]
    within_30   = [l for l in with_deadline if today <= (l.deadline_date or "") <= (datetime.now(timezone.utc)+timedelta(days=30)).strftime("%Y-%m-%d") and (l.update_needed or "").lower() not in ("none","optional")]
    completed   = sum(1 for l in with_deadline if (l.update_needed or "").lower() in ("none","optional"))
    total_active = len([l for l in all_libs if (l.update_needed or "").lower() in ("mandatory","recommended")])
    sla_pct = round((1 - len(overdue)/max(len(with_deadline),1)) * 100, 1)

    priority_counts = _priority_counts(all_libs)
    risk_score = _risk_score(priority_counts, len(all_libs))

    deprecated_count = sum(1 for l in all_libs if (l.status or "").lower() in ("deprecated", "legacy"))
    pie_distribution = {
        "critical": priority_counts.get("critical", 0) + priority_counts.get("mandatory", 0),
        "high": priority_counts.get("high", 0),
        "moderate": priority_counts.get("moderate", 0) + priority_counts.get("low", 0),
        "up_to_date": priority_counts.get("up_to_date", 0),
    }

    platforms = sorted({(l.platform or "Unknown") for l in all_libs})
    platform_distribution = []
    for platform in platforms:
        subset = [l for l in all_libs if (l.platform or "Unknown") == platform]
        counts = _priority_counts(subset)
        platform_distribution.append({
            "platform": platform,
            "critical": counts.get("critical", 0) + counts.get("mandatory", 0),
            "high": counts.get("high", 0),
            "moderate": counts.get("moderate", 0) + counts.get("low", 0),
            "up_to_date": counts.get("up_to_date", 0),
        })

    pending_lifecycle_rows = (await db.execute(
        select(UpgradeLifecycle, Library)
        .join(Library, Library.id == UpgradeLifecycle.library_id, isouter=True)
        .where(UpgradeLifecycle.status == "awaiting_review")
    )).all()
    pending_review_high_risk = sum(
        1 for row in pending_lifecycle_rows if _is_high_risk(row.Library.update_needed if row.Library else None)
    )

    # Lifecycle platform splits for Dashboard KPIs (backend-first, dedup by library)
    all_lifecycle_rows = (await db.execute(
        select(UpgradeLifecycle, Library)
        .join(Library, Library.id == UpgradeLifecycle.library_id, isouter=True)
    )).all()

    status_precedence = {
        "In Progress": 6,
        "Acknowledged": 5,
        "awaiting_review": 4,
        "Pending": 4,
        "Scheduled": 3,
        "Completed": 2,
        "Skipped": 1,
    }
    latest_by_library: dict[int, tuple[str, str]] = {}
    for row in all_lifecycle_rows:
        lc = row.UpgradeLifecycle
        lib = row.Library
        if not lc or not lib:
            continue
        platform = (lib.platform or "Unknown")
        existing = latest_by_library.get(lc.library_id)
        if existing is None:
            latest_by_library[lc.library_id] = (lc.status, platform)
            continue
        prev_status = existing[0]
        if (status_precedence.get(lc.status, 0) > status_precedence.get(prev_status, 0)):
            latest_by_library[lc.library_id] = (lc.status, platform)

    lifecycle_platform_split = {
        "in_progress": {"Android": 0, "iOS": 0, "Unknown": 0},
        "awaiting_review": {"Android": 0, "iOS": 0, "Unknown": 0},
    }
    for _lib_id, (status, platform) in latest_by_library.items():
        bucket = "in_progress" if status == "In Progress" else (
            "awaiting_review" if status in ("awaiting_review", "Pending") else None
        )
        if bucket is None:
            continue
        key = platform if platform in ("Android", "iOS") else "Unknown"
        lifecycle_platform_split[bucket][key] = lifecycle_platform_split[bucket].get(key, 0) + 1

    # Minimal backend-first forecast model: use current due pressure with conservative throughput.
    # Throughput is derived from completed lifecycle transitions in the last 14 days.
    now_utc = datetime.now(timezone.utc)
    start_14d = (now_utc - timedelta(days=14)).isoformat()
    recent_lifecycle = (await db.execute(
        select(UpgradeLifecycle).where(UpgradeLifecycle.updated_at >= start_14d)
    )).scalars().all()
    completed_recent = sum(1 for lc in recent_lifecycle if (lc.status or "").lower() == "completed")
    throughput_per_day = round(completed_recent / 14, 2) if completed_recent > 0 else 0.0

    due_7 = len(within_7)
    due_14 = len([
        l for l in with_deadline
        if today <= (l.deadline_date or "") <= (datetime.now(timezone.utc)+timedelta(days=14)).strftime("%Y-%m-%d")
        and (l.update_needed or "").lower() not in ("none", "optional")
    ])
    due_30 = len(within_30)
    forecast = {
        "throughput_per_day": throughput_per_day,
        "d7": max(0, int(round(due_7 - throughput_per_day * 7))),
        "d14": max(0, int(round(due_14 - throughput_per_day * 14))),
        "d30": max(0, int(round(due_30 - throughput_per_day * 30))),
        "model": "lifecycle-completion-velocity-v1",
    }

    today_dt = datetime.now(timezone.utc)
    at_risk_30d = []
    for lib in all_libs:
        if not lib.deadline_date:
            continue
        try:
            dl = datetime.strptime((lib.deadline_date or "")[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            continue
        days_left = int((dl - today_dt).days)
        if days_left <= 30:
            at_risk_30d.append((lib, days_left))

    at_risk_by_platform: dict[str, int] = {}
    for lib, _days_left in at_risk_30d:
        key = lib.platform or "Unknown"
        at_risk_by_platform[key] = (at_risk_by_platform.get(key, 0) + 1)

    latest_lifecycle_by_library: dict[int, UpgradeLifecycle] = {}
    for lc in recent_lifecycle:
        try:
            existing = latest_lifecycle_by_library.get(lc.library_id)
            existing_ts = datetime.fromisoformat((existing.updated_at or "").replace("Z", "+00:00")) if existing else None
            current_ts = datetime.fromisoformat((lc.updated_at or "").replace("Z", "+00:00"))
            if existing is None or current_ts > existing_ts:
                latest_lifecycle_by_library[lc.library_id] = lc
        except Exception:
            latest_lifecycle_by_library[lc.library_id] = lc

    at_risk_by_owner: dict[str, int] = {}
    for lib, _days_left in at_risk_30d:
        owner = (latest_lifecycle_by_library.get(lib.id).actioned_by if latest_lifecycle_by_library.get(lib.id) else "") or "Unassigned"
        at_risk_by_owner[owner] = at_risk_by_owner.get(owner, 0) + 1

    open_lifecycle = [lc for lc in recent_lifecycle if (lc.status or "").lower() != "completed"]
    owner_workload: dict[str, dict[str, int]] = {}
    seven_days_seconds = 7 * 24 * 60 * 60
    for item in open_lifecycle:
        owner = (item.actioned_by or "").strip() or "Unassigned"
        if owner not in owner_workload:
            owner_workload[owner] = {"critical": 0, "overdue": 0, "dueSoon": 0}
        lib = next((l for l in all_libs if l.id == item.library_id), None)
        if _is_high_risk(lib.update_needed if lib else None):
            owner_workload[owner]["critical"] += 1
        if item.target_date:
            try:
                due = datetime.fromisoformat(item.target_date.replace("Z", "+00:00"))
                delta_seconds = int((due - today_dt).total_seconds())
                if delta_seconds < 0:
                    owner_workload[owner]["overdue"] += 1
                elif delta_seconds <= seven_days_seconds:
                    owner_workload[owner]["dueSoon"] += 1
            except Exception:
                pass

    owner_workload_rows = [
        {
            "owner": owner,
            "critical": values["critical"],
            "overdue": values["overdue"],
            "dueSoon": values["dueSoon"],
            "total": values["critical"] + values["overdue"] + values["dueSoon"],
        }
        for owner, values in owner_workload.items()
    ]
    owner_workload_rows.sort(key=lambda x: x["total"], reverse=True)
    owner_workload_rows = owner_workload_rows[:5]

    rebalance_suggestion = "Workload looks balanced across current owners."
    if len(owner_workload_rows) >= 2:
        busiest = owner_workload_rows[0]
        lightest = owner_workload_rows[-1]
        delta = busiest["critical"] - lightest["critical"]
        if delta >= 3:
            rebalance_suggestion = (
                f"Reassign {min(3, delta)} high-priority items from {busiest['owner']} to {lightest['owner']} to reduce SLA breach risk."
            )
        else:
            rebalance_suggestion = "No immediate rebalancing required; continue monitoring overdue and due-soon queues."

    return ApiResponse.ok(
        data={
            "total_libraries":     len(all_libs),
            "with_deadline":       len(with_deadline),
            "overdue":             len(overdue),
            "due_within_7_days":   len(within_7),
            "due_within_30_days":  len(within_30),
            "completed_with_deadline": completed,
            "sla_compliance_pct":  sla_pct,
            "needs_upgrade":       total_active,
            "deprecated": deprecated_count,
            "priority_counts": priority_counts,
            "pie_distribution": pie_distribution,
            "platform_distribution": platform_distribution,
            "pending_review_high_risk": pending_review_high_risk,
            "lifecycle_platform_split": lifecycle_platform_split,
            "risk_score": risk_score,
            "sla_forecast": forecast,
            "at_risk_summary": {
                "by_platform": [{"name": k, "count": v} for k, v in sorted(at_risk_by_platform.items(), key=lambda x: x[1], reverse=True)[:3]],
                "by_owner": [{"name": k, "count": v} for k, v in sorted(at_risk_by_owner.items(), key=lambda x: x[1], reverse=True)[:3]],
            },
            "owner_workload": owner_workload_rows,
            "rebalance_suggestion": rebalance_suggestion,
            "backend_rules": {
                "enabled": settings.use_backend_business_rules,
                "source": "library-data-service:sla.summary:v1",
            },
        },
        meta=_meta()
    )


@router.get("/release-notes/{library_id}", response_model=ApiResponse[dict])
async def get_release_notes(
    library_id: int,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """
    Fetch release notes for a library from GitHub if repo_url is a GitHub URL.
    Falls back to returning what's in scrape_cache.release_notes.
    """
    lib = await db.get(Library, library_id)
    if lib is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Library {library_id} not found")

    notes: list[dict] = []
    source = "none"
    error = None

    # Try GitHub API if repo_url contains github.com
    if lib.repo_url and "github.com" in (lib.repo_url or ""):
        try:
            # Extract owner/repo from URL
            parts = lib.repo_url.rstrip("/").split("github.com/")[-1].split("/")
            if len(parts) >= 2:
                owner, repo = parts[0], parts[1].split(".git")[0]
                gh_url = f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=5"
                async with httpx.AsyncClient(timeout=8.0) as client:
                    resp = await client.get(gh_url, headers={"Accept": "application/vnd.github.v3+json"})
                if resp.status_code == 200:
                    releases = resp.json()
                    for r in releases[:5]:
                        body = r.get("body", "") or ""
                        notes.append({
                            "version":      r.get("tag_name",""),
                            "name":         r.get("name",""),
                            "published_at": (r.get("published_at",""))[:10],
                            "body":         body[:1000],
                            "url":          r.get("html_url",""),
                            "prerelease":   r.get("prerelease", False),
                        })
                    source = "github_api"
                else:
                    error = f"GitHub API returned {resp.status_code}"
        except Exception as exc:
            error = str(exc)[:100]

    return ApiResponse.ok(
        data={
            "library_id":   library_id,
            "package":      lib.package,
            "sdk_name":     lib.sdk_name,
            "repo_url":     lib.repo_url,
            "current_version": lib.current_version,
            "latest_version":  lib.latest_version,
            "source":       source,
            "notes_count":  len(notes),
            "release_notes": notes,
            "error":        error,
        },
        meta=_meta()
    )

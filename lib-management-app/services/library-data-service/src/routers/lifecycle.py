"""Router: /api/v1/lifecycle — upgrade lifecycle workflow."""
from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..exceptions import LibraryNotFoundError
from ..models.orm import Library, LibraryUpdateLog, LibraryVersion, UpgradeLifecycle
from ..models.schemas import (
    LifecycleBatchReviewRequest, LifecycleCompleteRequest, LifecycleInitRequest,
    LifecycleResponse, LifecycleSetActiveRequest, LifecycleUpdate, LifecycleWithLibraryResponse,
)
from ..repositories.other_repos import UpgradeLifecycleRepository
from ..repositories.library_repo import LibraryRepository
from shared.models.base_schemas import ApiResponse, ResponseMeta

router = APIRouter(prefix="/api/v1/lifecycle", tags=["lifecycle"])


def _meta() -> ResponseMeta:
    return ResponseMeta(service=settings.service_name, version=settings.service_version)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_business_critical(update_needed: str | None, priority: str | None) -> bool:
    urgency = (update_needed or "").lower()
    pri = (priority or "").lower()
    return urgency in ("mandatory", "critical", "high") or pri == "high"


def _derive_priority(current: str | None, latest: str | None) -> str:
    """Derive update_needed from version gap after activation."""
    if not current or not latest or current.strip() == latest.strip():
        return "none"
    try:
        from packaging.version import Version
        c, l = Version(current.lstrip("v")), Version(latest.lstrip("v"))
        if c >= l:
            return "none"
        if l.major > c.major:
            return "mandatory"
        if l.minor > c.minor:
            return "recommended"
        return "optional"
    except Exception:
        return "none"


def _confidence_score(update_needed: str | None, current_version: str | None, latest_version: str | None, ai_summary: str | None = None) -> tuple[int, str]:
    score = 45
    urgency = (update_needed or "").lower()

    if urgency in ("mandatory", "critical"):
        score += 20
    elif urgency == "high":
        score += 14
    elif urgency == "moderate":
        score += 8

    if current_version and latest_version and current_version != latest_version:
        score += 12
    if (ai_summary or "").strip() and len((ai_summary or "").strip()) >= 40:
        score += 12

    bounded = max(0, min(100, score))
    if bounded >= 75:
        return bounded, "High"
    if bounded >= 55:
        return bounded, "Medium"
    return bounded, "Low"


def _to_lifecycle_with_library(lc: UpgradeLifecycle, lib: Library | None) -> LifecycleWithLibraryResponse:
    confidence_score, confidence_band = _confidence_score(
        lib.update_needed if lib else None,
        lib.current_version if lib else None,
        lib.latest_version if lib else None,
        None,
    )
    return LifecycleWithLibraryResponse(
        id=lc.id,
        library_id=lc.library_id,
        recommendation_id=lc.recommendation_id,
        status=lc.status,
        target_version=lc.target_version,
        target_sprint=lc.target_sprint,
        target_date=lc.target_date,
        completed_version=lc.completed_version,
        skip_reason=lc.skip_reason,
        actioned_by=lc.actioned_by,
        created_at=lc.created_at,
        updated_at=lc.updated_at,
        package=lib.package if lib else None,
        sdk_name=lib.sdk_name if lib else None,
        platform=lib.platform if lib else None,
        current_version=lib.current_version if lib else None,
        latest_version=lib.latest_version if lib else None,
        update_needed=lib.update_needed if lib else None,
        priority=lib.priority if lib else None,
        business_critical=_is_business_critical(lib.update_needed if lib else None, lib.priority if lib else None),
        confidence_score=confidence_score,
        confidence_band=confidence_band,
    )


@router.get("", response_model=ApiResponse[list[LifecycleWithLibraryResponse]])
async def list_lifecycles(
    status: str | None = None,
    platform: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[LifecycleWithLibraryResponse]]:
    """List all lifecycle entries with their library details."""
    stmt = (
        select(UpgradeLifecycle, Library)
        .join(Library, Library.id == UpgradeLifecycle.library_id, isouter=True)
        .order_by(UpgradeLifecycle.updated_at.desc())
    )
    if status:
        stmt = stmt.where(UpgradeLifecycle.status == status)
    if platform:
        stmt = stmt.where(Library.platform == platform)

    rows = (await db.execute(stmt)).all()
    data = [_to_lifecycle_with_library(row.UpgradeLifecycle, row.Library) for row in rows]
    return ApiResponse.ok(data=data, meta=_meta())


@router.get("/{library_id}", response_model=ApiResponse[LifecycleWithLibraryResponse | None])
async def get_library_lifecycle(
    library_id: int,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[LifecycleWithLibraryResponse | None]:
    """Get the active lifecycle entry for a specific library."""
    lib_repo = LibraryRepository(db)
    lc_repo = UpgradeLifecycleRepository(db)
    lib = await lib_repo.get_by_id(library_id)
    lc = await lc_repo.get_by_library(library_id)
    if lc is None:
        return ApiResponse.ok(data=None, meta=_meta())
    return ApiResponse.ok(data=_to_lifecycle_with_library(lc, lib), meta=_meta())


@router.post("", response_model=ApiResponse[LifecycleWithLibraryResponse], status_code=201)
async def init_lifecycle(
    body: LifecycleInitRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[LifecycleWithLibraryResponse]:
    """Create or re-open a lifecycle entry (Pending) for a library."""
    lib_repo = LibraryRepository(db)
    lc_repo = UpgradeLifecycleRepository(db)
    lib = await lib_repo.get_by_id(body.library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail=f"Library {body.library_id} not found")
    lc = await lc_repo.upsert(body.library_id, body.recommendation_id, body.target_version)
    await db.commit()
    await db.refresh(lc)
    return ApiResponse.ok(data=_to_lifecycle_with_library(lc, lib), meta=_meta())


@router.put("/{lifecycle_id}", response_model=ApiResponse[LifecycleWithLibraryResponse])
async def update_lifecycle(
    lifecycle_id: int,
    body: LifecycleUpdate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[LifecycleWithLibraryResponse]:
    """Update lifecycle status (Acknowledged / Scheduled / In Progress / Skipped).
    NOTE: Use the dedicated /decline endpoint to roll back from In Progress → Acknowledged.
    """
    lc_repo = UpgradeLifecycleRepository(db)
    kwargs = body.model_dump(exclude={"status", "actioned_by"}, exclude_none=True)
    lc = await lc_repo.update_status(lifecycle_id, body.status, body.actioned_by, **kwargs)
    if lc is None:
        raise HTTPException(status_code=404, detail=f"Lifecycle {lifecycle_id} not found")
    lib = await db.get(Library, lc.library_id)
    await db.commit()
    await db.refresh(lc)
    return ApiResponse.ok(data=_to_lifecycle_with_library(lc, lib), meta=_meta())


@router.put("/{lifecycle_id}/complete", response_model=ApiResponse[LifecycleWithLibraryResponse])
async def complete_lifecycle(
    lifecycle_id: int,
    body: LifecycleCompleteRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[LifecycleWithLibraryResponse]:
    """
    Mark upgrade as Completed.
    Also updates library.current_version and writes audit log.
    """
    lc = await db.get(UpgradeLifecycle, lifecycle_id)
    if lc is None:
        raise HTTPException(status_code=404, detail=f"Lifecycle {lifecycle_id} not found")

    lib_repo = LibraryRepository(db)
    lib = await lib_repo.get_by_id(lc.library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail=f"Library {lc.library_id} not found")

    # Update lifecycle
    lc.status = "Completed"
    lc.completed_version = body.completed_version
    lc.actioned_by = body.actioned_by
    lc.updated_at = _now()

    # Update library current_version → auto-derives update_needed from version gap
    old_version = lib.current_version
    lib.current_version = body.completed_version
    lib.update_needed = _derive_priority(body.completed_version, lib.latest_version)
    lib.last_checked_date = _now()[:10]
    lib.updated_at = _now()

    # Write audit log
    db.add(LibraryUpdateLog(
        library_id=lib.id,
        updated_by=body.actioned_by,
        update_type="lifecycle_complete",
        field_changed="current_version",
        old_value=old_version,
        new_value=body.completed_version,
        reason=body.reason or f"Upgrade completed via lifecycle workflow. PR: {body.pr_url or 'N/A'}",
        updated_at=_now(),
    ))

    await db.commit()
    await db.refresh(lc)
    await db.refresh(lib)
    return ApiResponse.ok(data=_to_lifecycle_with_library(lc, lib), meta=_meta())


@router.put("/{lifecycle_id}/set-active", response_model=ApiResponse[LifecycleWithLibraryResponse])
async def set_version_active(
    lifecycle_id: int,
    body: LifecycleSetActiveRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[LifecycleWithLibraryResponse]:
    """
    Set a specific version as the Active/current version.
    - Marks lifecycle as Completed.
    - Sets library.current_version = target_version.
    - Sets library.status = "Active".
    - Writes mandatory comment to audit log.
    Body: { target_version, comment (mandatory), actioned_by }
    """
    lc = await db.get(UpgradeLifecycle, lifecycle_id)
    if lc is None:
        raise HTTPException(status_code=404, detail=f"Lifecycle {lifecycle_id} not found")

    # Enforce strict transition: must be In Progress before setting Active
    if lc.status != "In Progress":
        raise HTTPException(
            status_code=422,
            detail=f"Cannot set Active from '{lc.status}'. Move to In Progress first, then set Active.",
        )

    normalized_target_version = (body.target_version or "").strip()
    if not normalized_target_version:
        raise HTTPException(status_code=422, detail="Target version is required")

    lc_target = (lc.target_version or "").strip()
    if not lc_target:
        raise HTTPException(
            status_code=422,
            detail="Lifecycle target version is missing. Mark In Progress with a target version first.",
        )
    if normalized_target_version != lc_target:
        raise HTTPException(
            status_code=422,
            detail=(
                "Target version mismatch with active In Progress lifecycle. "
                "Select the version for review and complete Acknowledged -> In Progress again before Set Active."
            ),
        )

    lib_repo = LibraryRepository(db)
    lib = await lib_repo.get_by_id(lc.library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail=f"Library {lc.library_id} not found")

    old_version = lib.current_version
    old_status  = lib.status

    # Update lifecycle
    lc.status           = "Completed"
    lc.completed_version = normalized_target_version
    lc.target_version   = normalized_target_version
    lc.actioned_by      = body.actioned_by
    lc.skip_reason      = body.comment
    lc.updated_at       = _now()

    # Update library — set version, derive priority from gap, mark Active
    lib.current_version   = normalized_target_version
    lib.status            = "Active"
    lib.update_needed     = _derive_priority(normalized_target_version, lib.latest_version)
    lib.last_checked_date = _now()[:10]
    lib.updated_at        = _now()

    # Keep version-history current flags in sync with newly activated version.
    version_rows = (await db.execute(
        select(LibraryVersion).where(LibraryVersion.library_id == lib.id)
    )).scalars().all()
    for row in version_rows:
        row.is_current = (row.version == normalized_target_version)

    # Audit log entry — comment is the mandatory reason
    db.add(LibraryUpdateLog(
        library_id=lib.id,
        updated_by=body.actioned_by,
        update_type="set_active",
        field_changed="current_version",
        old_value=old_version,
        new_value=normalized_target_version,
        reason=body.comment,
        updated_at=_now(),
    ))

    # Second audit entry if status changed
    if old_status != "Active":
        db.add(LibraryUpdateLog(
            library_id=lib.id,
            updated_by=body.actioned_by,
            update_type="status_change",
            field_changed="status",
            old_value=old_status,
            new_value="Active",
            reason=body.comment,
            updated_at=_now(),
        ))

    await db.commit()
    await db.refresh(lc)
    await db.refresh(lib)
    return ApiResponse.ok(data=_to_lifecycle_with_library(lc, lib), meta=_meta())


@router.put("/{lifecycle_id}/in-progress", response_model=ApiResponse[LifecycleWithLibraryResponse])
async def mark_in_progress(
    lifecycle_id: int,
    body: LifecycleUpdate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[LifecycleWithLibraryResponse]:
    """
    Move lifecycle to In Progress state.
    Convenience endpoint — same as PUT /{id} with status='In Progress'.
    """
    lc_repo = UpgradeLifecycleRepository(db)
    kwargs = body.model_dump(exclude={"status", "actioned_by"}, exclude_none=True)
    lc = await lc_repo.update_status(lifecycle_id, "In Progress", body.actioned_by, **kwargs)
    if lc is None:
        raise HTTPException(status_code=404, detail=f"Lifecycle {lifecycle_id} not found")
    lib = await db.get(Library, lc.library_id)
    await db.commit()
    await db.refresh(lc)
    return ApiResponse.ok(data=_to_lifecycle_with_library(lc, lib), meta=_meta())


@router.put("/{lifecycle_id}/decline", response_model=ApiResponse[LifecycleWithLibraryResponse])
async def decline_lifecycle(
    lifecycle_id: int,
    body: LifecycleUpdate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[LifecycleWithLibraryResponse]:
    """
    Decline an in-progress upgrade — rolls back to Acknowledged and clears target_version.
    Only allowed when current status is 'In Progress'.
    """
    lc = await db.get(UpgradeLifecycle, lifecycle_id)
    if lc is None:
        raise HTTPException(status_code=404, detail=f"Lifecycle {lifecycle_id} not found")
    if lc.status != "In Progress":
        raise HTTPException(
            status_code=422,
            detail=f"Cannot decline from '{lc.status}'. Decline is only allowed from 'In Progress'.",
        )
    lc.status = "Acknowledged"
    lc.target_version = None
    lc.actioned_by = body.actioned_by
    lc.updated_at = _now()
    lib = await db.get(Library, lc.library_id)
    await db.commit()
    await db.refresh(lc)
    return ApiResponse.ok(data=_to_lifecycle_with_library(lc, lib), meta=_meta())


@router.get("/pending/review", response_model=ApiResponse[list[dict]])
async def get_pending_review(
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[dict]]:
    """
    Return all libraries awaiting HITL review — joined with recommendations.
    Returns rich data for the review UI: library info + AI recommendation + lifecycle id.
    """
    from sqlalchemy import text
    rows = (await db.execute(
        select(UpgradeLifecycle, Library)
        .join(Library, Library.id == UpgradeLifecycle.library_id, isouter=True)
        .where(UpgradeLifecycle.status == "awaiting_review")
        .order_by(Library.platform, Library.update_needed.desc(), Library.priority)
    )).all()

    # Fetch latest recommendation per library
    from ..models.orm import Recommendation
    import json

    data = []
    for row in rows:
        lc  = row.UpgradeLifecycle
        lib = row.Library
        # Get latest recommendation
        rec_row = (await db.execute(
            select(Recommendation)
            .where(Recommendation.library_id == lc.library_id)
            .order_by(Recommendation.generated_at.desc())
            .limit(1)
        )).scalar_one_or_none()

        def _parse_json(val):
            if not val: return []
            try: return json.loads(val)
            except Exception: return []

        confidence_score, confidence_band = _confidence_score(
            lib.update_needed if lib else None,
            lib.current_version if lib else None,
            lib.latest_version if lib else None,
            rec_row.recommendation_summary if rec_row else None,
        )

        data.append({
            "lifecycle_id":   lc.id,
            "library_id":     lc.library_id,
            "package":        lib.package if lib else "—",
            "sdk_name":       lib.sdk_name if lib else None,
            "platform":       lib.platform if lib else "—",
            "framework_language": lib.framework_language if lib else None,
            "current_version":lib.current_version if lib else "—",
            "latest_version": lib.latest_version if lib else "—",
            "update_needed":  lib.update_needed if lib else "none",
            "status":         lib.status if lib else "Unknown",
            "priority":       lib.priority if lib else "Medium",
            "alert_priority": lib.alert_priority if lib else "Normal",
            "deadline_date":  lib.deadline_date if lib else None,
            "deprecation_notes": lib.deprecation_notes if lib else None,
            "lifecycle_status": lc.status,
            "lifecycle_updated": lc.updated_at,
            "ai_recommendation":  rec_row.upgrade_recommended if rec_row else None,
            "ai_summary":         rec_row.recommendation_summary if rec_row else None,
            "upgrade_pros":       _parse_json(rec_row.upgrade_pros) if rec_row else [],
            "upgrade_cons":       _parse_json(rec_row.upgrade_cons) if rec_row else [],
            "no_upgrade_pros":    _parse_json(rec_row.no_upgrade_pros) if rec_row else [],
            "business_critical": _is_business_critical(lib.update_needed if lib else None, lib.priority if lib else None),
            "confidence_score": confidence_score,
            "confidence_band": confidence_band,
        })
    return ApiResponse.ok(data=data, meta=_meta())


@router.post("/batch-review", status_code=201)
async def create_batch_review(
    body: LifecycleBatchReviewRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Called by scheduler after batch_recommend step.
    Creates/resets lifecycle entries to awaiting_review for ALL libraries.
    This kicks off the HITL review workflow.
    """
    created = updated = 0
    now = _now()
    for lib_item in body.libraries:
        lid = lib_item.get("library_id")
        if not lid:
            continue
        existing = (await db.execute(
            select(UpgradeLifecycle)
            .where(UpgradeLifecycle.library_id == lid)
            .order_by(UpgradeLifecycle.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()

        if existing and existing.status in ("Pending","awaiting_review"):
            # Reset to awaiting_review for fresh review
            existing.status = "awaiting_review"
            existing.skip_reason = None
            existing.actioned_by = f"pipeline:{body.run_id[:8]}"
            existing.updated_at = now
            updated += 1
        else:
            # Create new awaiting_review entry
            db.add(UpgradeLifecycle(
                library_id=lid,
                status="awaiting_review",
                actioned_by=f"pipeline:{body.run_id[:8]}",
                created_at=now,
                updated_at=now,
            ))
            created += 1

    await db.commit()
    return {"created": created, "updated": updated, "total": created + updated}


@router.put("/{lifecycle_id}/approve-no-action")
async def approve_no_action(
    lifecycle_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[LifecycleWithLibraryResponse]:
    """Mark a 'no action needed' library as reviewed and acknowledged."""
    lc = await db.get(UpgradeLifecycle, lifecycle_id)
    if lc is None:
        raise HTTPException(status_code=404, detail=f"Lifecycle {lifecycle_id} not found")
    lc.status = "Acknowledged"
    lc.actioned_by = body.get("actioned_by", "admin")
    lc.skip_reason = "Confirmed: no upgrade required at this time"
    lc.updated_at  = _now()
    lib = await db.get(Library, lc.library_id)
    await db.commit()
    await db.refresh(lc)
    return ApiResponse.ok(data=_to_lifecycle_with_library(lc, lib), meta=_meta())


@router.put("/{lifecycle_id}/reject")
async def reject_upgrade(
    lifecycle_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[LifecycleWithLibraryResponse]:
    """Reject/defer an upgrade. Sets lifecycle to Skipped with reason."""
    lc = await db.get(UpgradeLifecycle, lifecycle_id)
    if lc is None:
        raise HTTPException(status_code=404, detail=f"Lifecycle {lifecycle_id} not found")
    lc.status     = "Skipped"
    lc.actioned_by = body.get("actioned_by", "admin")
    lc.skip_reason = body.get("reason", "Deferred by reviewer")
    lc.updated_at  = _now()
    lib = await db.get(Library, lc.library_id)
    await db.commit()
    await db.refresh(lc)
    return ApiResponse.ok(data=_to_lifecycle_with_library(lc, lib), meta=_meta())

"""Business analytics router for backend-owned UI rule computations."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException

from ..auth.dependencies import get_current_user
from ..config import settings

router = APIRouter(prefix="/api/v1/business", tags=["business"], dependencies=[Depends(get_current_user)])

_INTERNAL_HEADERS = {"X-Internal-Service-Key": settings.internal_service_key}
_TIMEOUT = 30.0


def _unwrap(payload: object) -> object:
    if isinstance(payload, dict) and "data" in payload:
        return payload.get("data")
    return payload


def _is_retry_message(message: str) -> bool:
    value = (message or "").strip().lower()
    if not value:
        return False
    return (
        "retry" in value
        or "attempt" in value
        or "[retry]" in value
    )


def _classify_failure_reason(message: str) -> str:
    m = (message or "").lower()
    if any(key in m for key in ("auth", "unauthorized", "forbidden", "credential", "invalid api key")):
        return "Auth Failure"
    if any(key in m for key in ("timeout", "timed out", "deadline exceeded", "socket hang up")):
        return "Timeout"
    if any(key in m for key in ("recipient", "mailbox", "invalid email", "email address", "rcpt")):
        return "Invalid Recipient"
    if "webhook" in m and any(key in m for key in ("invalid", "not found", "malformed", "404", "410")):
        return "Invalid Webhook"
    return "Other Delivery Errors"


def _safe_ts(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


async def _get_json(client: httpx.AsyncClient, url: str) -> object:
    resp = await client.get(url, headers=_INTERNAL_HEADERS)
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Upstream request failed ({resp.status_code}) for {url}")
    return _unwrap(resp.json())


@router.get("/weekly-digest")
async def weekly_digest() -> dict:
    """Compute weekly digest on backend so UI stays presentation-only."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        libs_raw = await _get_json(client, f"{settings.library_data_service_url}/api/v1/libraries?limit=1000")
        sla_raw = await _get_json(client, f"{settings.library_data_service_url}/api/v1/sla/summary")
        runs_raw = await _get_json(client, f"{settings.scheduler_service_url}/api/v1/runs")
        lifecycle_raw = await _get_json(client, f"{settings.library_data_service_url}/api/v1/lifecycle?limit=500")
        notifications_raw = await _get_json(client, f"{settings.notification_service_url}/api/v1/notifications")

    libs = (libs_raw or {}).get("libraries", []) if isinstance(libs_raw, dict) else []
    sla = sla_raw if isinstance(sla_raw, dict) else {}
    runs = runs_raw if isinstance(runs_raw, list) else []
    lifecycle = lifecycle_raw if isinstance(lifecycle_raw, list) else []
    notifications = notifications_raw if isinstance(notifications_raw, list) else []

    now = datetime.now(timezone.utc)
    now_ts = now.timestamp()
    seven_days_seconds = 7 * 24 * 60 * 60

    priority_counts = (sla.get("priority_counts") or {}) if isinstance(sla, dict) else {}
    critical = int(priority_counts.get("critical", 0)) + int(priority_counts.get("mandatory", 0)) + int(priority_counts.get("high", 0))
    portfolio_risk = round((critical / max(len(libs), 1)) * 100) if libs else 0

    recent_runs = [
        r for r in runs
        if now_ts - _safe_ts((r or {}).get("started_at")) <= seven_days_seconds
    ]
    completed_recent = sum(1 for r in recent_runs if str((r or {}).get("status", "")).lower() == "completed")
    pipeline_reliability = round((completed_recent / len(recent_runs)) * 100) if recent_runs else 100

    approvals_processed_7d = sum(
        1 for l in lifecycle
        if now_ts - _safe_ts((l or {}).get("updated_at")) <= seven_days_seconds
        and str((l or {}).get("status", "")).lower() in ("acknowledged", "completed", "in progress")
    )

    rows = []
    for entry in notifications:
        for res in (entry or {}).get("results", []) or []:
            rows.append({
                "channel": str((res or {}).get("channel", "")).lower(),
                "status": str((res or {}).get("status", "")).lower(),
                "message": str((res or {}).get("message", "")).strip(),
                "at": (res or {}).get("sent_at") or (entry or {}).get("generated_at"),
            })

    sent = sum(1 for r in rows if r["status"] == "sent")
    failed = sum(1 for r in rows if r["status"] == "failed")
    delivery_pct = round((sent / (sent + failed)) * 100) if sent + failed > 0 else 100
    retry_count = sum(1 for r in rows if _is_retry_message(r["message"]))

    pipeline_by_status_7d = {
        "completed": sum(1 for r in recent_runs if str((r or {}).get("status", "")).lower() == "completed"),
        "failed": sum(1 for r in recent_runs if str((r or {}).get("status", "")).lower() == "failed"),
        "partial": sum(1 for r in recent_runs if str((r or {}).get("status", "")).lower() == "partial"),
    }

    latest_lifecycle_by_library: dict[int, dict] = {}
    for row in lifecycle:
        library_id = (row or {}).get("library_id")
        if library_id is None:
            continue
        prev = latest_lifecycle_by_library.get(int(library_id))
        if prev is None or _safe_ts((row or {}).get("updated_at")) > _safe_ts((prev or {}).get("updated_at")):
            latest_lifecycle_by_library[int(library_id)] = row

    channels = ["email", "teams"]
    channel_summary = []
    for channel in channels:
        subset = [r for r in rows if r["channel"] == channel]
        c_sent = sum(1 for r in subset if r["status"] == "sent")
        c_failed = sum(1 for r in subset if r["status"] == "failed")
        c_base = c_sent + c_failed
        channel_summary.append({
            "channel": channel,
            "sent": c_sent,
            "failed": c_failed,
            "retries": sum(1 for r in subset if _is_retry_message(r["message"])),
            "deliveryPct": round((c_sent / c_base) * 100) if c_base > 0 else 100,
        })

    failure_buckets: dict[str, int] = {}
    for row in [r for r in rows if r["status"] == "failed"]:
        bucket = _classify_failure_reason(row["message"])
        failure_buckets[bucket] = failure_buckets.get(bucket, 0) + 1
    top_failure_reasons = [
        {"reason": reason, "count": count}
        for reason, count in sorted(failure_buckets.items(), key=lambda item: item[1], reverse=True)[:4]
    ]

    platform_risk = []
    platforms = sorted({str((l or {}).get("platform") or "Unknown") for l in libs})
    for platform in platforms:
        subset = [l for l in libs if (l or {}).get("platform") == platform]
        overdue = 0
        for item in subset:
            deadline = (item or {}).get("deadline_date")
            if deadline and _safe_ts(f"{str(deadline)[:10]}T00:00:00+00:00") < now_ts:
                overdue += 1
        critical_count = sum(
            1
            for l in subset
            if str((l or {}).get("update_needed", "")).lower() in ("mandatory", "critical", "high")
        )
        platform_risk.append({
            "platform": platform,
            "total": len(subset),
            "critical": critical_count,
            "overdue": overdue,
        })

    overdue_libraries = []
    for lib in libs:
        deadline = (lib or {}).get("deadline_date")
        if not deadline:
            continue
        due_ts = _safe_ts(f"{str(deadline)[:10]}T00:00:00+00:00")
        delta_days = int((due_ts - now_ts) // (24 * 60 * 60))
        if delta_days >= 0:
            continue
        library_id = int((lib or {}).get("id", 0))
        latest = latest_lifecycle_by_library.get(library_id, {})
        overdue_libraries.append({
            "id": library_id,
            "package": (lib or {}).get("package"),
            "platform": (lib or {}).get("platform"),
            "priority": (lib or {}).get("update_needed"),
            "daysOverdue": abs(delta_days),
            "owner": (latest or {}).get("actioned_by") or "Unassigned",
            "isOverdue": True,
        })
    overdue_libraries.sort(key=lambda item: item["daysOverdue"], reverse=True)
    overdue_libraries = overdue_libraries[:8]

    approvals_by_status_7d = {
        "completed": sum(
            1 for l in lifecycle
            if now_ts - _safe_ts((l or {}).get("updated_at")) <= seven_days_seconds
            and str((l or {}).get("status", "")).lower() == "completed"
        ),
        "acknowledged": sum(
            1 for l in lifecycle
            if now_ts - _safe_ts((l or {}).get("updated_at")) <= seven_days_seconds
            and str((l or {}).get("status", "")).lower() == "acknowledged"
        ),
        "inProgress": sum(
            1 for l in lifecycle
            if now_ts - _safe_ts((l or {}).get("updated_at")) <= seven_days_seconds
            and str((l or {}).get("status", "")).lower() == "in progress"
        ),
    }

    return {
        "generated_at": now.isoformat(),
        "portfolio_risk_trend_pct": portfolio_risk,
        "approvals_processed_7d": approvals_processed_7d,
        "overdue_now": int(sla.get("overdue", 0)),
        "due_7d": int(sla.get("due_within_7_days", 0)),
        "due_30d": int(sla.get("due_within_30_days", 0)),
        "pipeline_reliability_7d_pct": pipeline_reliability,
        "notification_health_pct": delivery_pct,
        "notification_retry_count": retry_count,
        "sla_compliance_pct": float(sla.get("sla_compliance_pct", 0) or 0),
        "pipeline_by_status_7d": pipeline_by_status_7d,
        "approvals_by_status_7d": approvals_by_status_7d,
        "channel_summary": channel_summary,
        "top_failure_reasons": top_failure_reasons,
        "platform_risk": platform_risk,
        "top_overdue_libraries": overdue_libraries,
        "backend_rules": {
            "enabled": settings.use_backend_business_rules,
            "source": "api-gateway:business.weekly-digest:v1",
        },
    }

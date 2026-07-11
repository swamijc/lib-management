"""
API Gateway — health router.

GET /health         — gateway own health (no auth)
GET /health/services — aggregate health from all backends (no auth)
"""
from __future__ import annotations

import asyncio
import httpx
from fastapi import APIRouter
from fastapi import Request

from ..config import settings

router = APIRouter(tags=["health"])

_SERVICES = {
    "library-data-service": settings.library_data_service_url,
    "scraper-service":       settings.scraper_service_url,
    "comparison-service":    settings.comparison_service_url,
    "recommendation-service": settings.recommendation_service_url,
    "notification-service":  settings.notification_service_url,
    "scheduler-service":     settings.scheduler_service_url,
}


async def _check_service(name: str, base_url: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url}/health")
        return {"service": name, "status": "healthy" if resp.status_code == 200 else "degraded",
                "status_code": resp.status_code}
    except Exception as exc:
        return {"service": name, "status": "unreachable", "error": str(exc)}


async def _check_service_runtime(name: str, base_url: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(f"{base_url}/health/runtime")
        payload = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        runtime = payload.get("runtime") if isinstance(payload, dict) else None
        return {
            "service": name,
            "status": "healthy" if resp.status_code == 200 and runtime else "degraded",
            "status_code": resp.status_code,
            "runtime": runtime,
        }
    except Exception as exc:
        return {
            "service": name,
            "status": "unreachable",
            "error": str(exc),
            "runtime": None,
        }


@router.get("/health")
async def health() -> dict:
    return {
        "status": "healthy",
        "service": settings.service_name,
        "version": settings.service_version,
    }


@router.get("/health/services")
async def services_health() -> dict:
    results = await asyncio.gather(*[
        _check_service(name, url) for name, url in _SERVICES.items()
    ])
    all_ok = all(r["status"] == "healthy" for r in results)
    return {
        "gateway_status": "healthy",
        "overall": "healthy" if all_ok else "degraded",
        "services": list(results),
    }


@router.get("/health/runtime")
async def runtime_health(request: Request) -> dict:
    telemetry = getattr(request.app.state, "runtime_telemetry", None)
    if telemetry is None:
        return {
            "gateway_status": "healthy",
            "runtime": None,
            "message": "Runtime telemetry is not initialized",
        }
    snapshot = await telemetry.snapshot(top_n=10)
    service_runtimes = await asyncio.gather(*[
        _check_service_runtime(name, url) for name, url in _SERVICES.items()
    ])

    aggregate_requests = 0
    aggregate_errors = 0
    aggregate_memory_mb = 0.0
    aggregate_cpu_pct = 0.0
    healthy_runtime_services = 0

    for svc in service_runtimes:
        runtime = svc.get("runtime") or {}
        req = (runtime.get("requests") or {}) if isinstance(runtime, dict) else {}
        res = (runtime.get("resources") or {}) if isinstance(runtime, dict) else {}
        aggregate_requests += int(req.get("total") or 0)
        aggregate_errors += int(req.get("errors") or 0)
        aggregate_memory_mb += float(res.get("memory_rss_mb") or 0.0)
        aggregate_cpu_pct += float(res.get("cpu_percent") or 0.0)
        if svc.get("status") == "healthy":
            healthy_runtime_services += 1

    thresholds = {
        "errorRatePct": 2,
        "latencyMs": 500,
        "memoryMb": 700,
    }

    req_windows = (snapshot.get("requests") or {}).get("windows") or {}
    last_5m = req_windows.get("last_5m") or {}
    resources = snapshot.get("resources") or {}

    threshold_alerts = [
        msg for msg in [
            (
                f"5m error rate {float(last_5m.get('error_rate_pct') or 0):.2f}% exceeds {thresholds['errorRatePct']}%"
                if float(last_5m.get("error_rate_pct") or 0) > thresholds["errorRatePct"]
                else None
            ),
            (
                f"5m avg latency {float(last_5m.get('avg_latency_ms') or 0):.2f}ms exceeds {thresholds['latencyMs']}ms"
                if float(last_5m.get("avg_latency_ms") or 0) > thresholds["latencyMs"]
                else None
            ),
            (
                f"Gateway memory {float(resources.get('memory_rss_mb') or 0):.2f}MB exceeds {thresholds['memoryMb']}MB"
                if float(resources.get("memory_rss_mb") or 0) > thresholds["memoryMb"]
                else None
            ),
        ]
        if msg
    ]

    policy_drift_alerts: list[dict] = []
    if unhealthy_runtime_services := len([s for s in service_runtimes if s.get("status") != "healthy"]):
        policy_drift_alerts.append({
            "id": "service-health-drift",
            "title": f"{unhealthy_runtime_services} service(s) unhealthy",
            "severity": "medium",
            "status": "drift",
            "impact": [
                "Policy controls may not apply uniformly across services",
                "Operational dashboards can show delayed or incomplete telemetry",
            ],
            "affectedAreas": ["Service Health", "Metrics Collection"],
            "recommendation": "Resolve unhealthy services and verify runtime telemetry freshness.",
        })

    if threshold_alerts:
        policy_drift_alerts.append({
            "id": "runtime-threshold-drift",
            "title": "Runtime thresholds exceeded",
            "severity": "high",
            "status": "drift",
            "impact": [
                "Increased risk of SLA variance due to runtime instability",
                "Higher chance of delayed recommendations and notifications",
            ],
            "affectedAreas": ["Runtime Telemetry", "SLA Forecasting", "Pipeline Reliability"],
            "recommendation": "Stabilize latency/error/memory metrics and re-check threshold status.",
        })

    summary = {
        "total": len(policy_drift_alerts),
        "high": len([d for d in policy_drift_alerts if d.get("severity") == "high"]),
        "medium": len([d for d in policy_drift_alerts if d.get("severity") == "medium"]),
        "low": len([d for d in policy_drift_alerts if d.get("severity") == "low"]),
    }

    return {
        "gateway_status": "healthy",
        "runtime": snapshot,
        "services_runtime": service_runtimes,
        "thresholds": thresholds,
        "threshold_alerts": threshold_alerts,
        "policy_drift_alerts": policy_drift_alerts,
        "policy_drift_summary": summary,
        "backend_rules": {
            "enabled": settings.use_backend_business_rules,
            "source": "api-gateway:health.runtime:v1",
        },
        "services_runtime_summary": {
            "services_total": len(service_runtimes),
            "services_with_runtime": healthy_runtime_services,
            "aggregate_requests": aggregate_requests,
            "aggregate_errors": aggregate_errors,
            "aggregate_error_rate_pct": round((aggregate_errors / aggregate_requests * 100.0), 2) if aggregate_requests > 0 else 0.0,
            "aggregate_memory_rss_mb": round(aggregate_memory_mb, 2),
            "aggregate_cpu_percent": round(aggregate_cpu_pct, 2),
        },
    }

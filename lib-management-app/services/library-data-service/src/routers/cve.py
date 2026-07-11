"""Router: /api/v1/cve — CVE scanning via OSV.dev (free, no API key)."""
from __future__ import annotations
import json
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models.orm import CveCache, Library
from shared.models.base_schemas import ApiResponse, ResponseMeta

router = APIRouter(prefix="/api/v1/cve", tags=["cve"])

_OSV_URL = "https://api.osv.dev/v1/query"
_OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"

# Map our registry/platform to OSV.dev ecosystem names
_ECOSYSTEM_MAP = {
    "maven":     "Maven",
    "cocoapods": "CocoaPods",
    "spm":       "Swift URL",
    "npm":       "npm",
    "pypi":      "PyPI",
    "github":    "GitHub Actions",
}
_PLATFORM_ECOSYSTEM = {
    "Android": "Maven",
    "iOS":     "CocoaPods",
    "Both":    "Maven",
}


def _meta() -> ResponseMeta:
    return ResponseMeta(service=settings.service_name, version=settings.service_version)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _detect_ecosystem(lib: Library) -> str:
    if lib.registry and lib.registry.lower() in _ECOSYSTEM_MAP:
        return _ECOSYSTEM_MAP[lib.registry.lower()]
    return _PLATFORM_ECOSYSTEM.get(lib.platform, "Maven")


async def _osv_query(package: str, ecosystem: str, version: str) -> list[dict]:
    """Query OSV.dev for vulnerabilities. Returns list of vuln summaries."""
    payload = {
        "package": {"name": package, "ecosystem": ecosystem},
        "version": version,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(_OSV_URL, json=payload)
            if resp.status_code != 200:
                return []
            data = resp.json()
            vulns = data.get("vulns", [])
            return [
                {
                    "id":       v.get("id", ""),
                    "summary":  v.get("summary", "")[:200],
                    "severity": _extract_severity(v),
                    "cvss":     _extract_cvss(v),
                    "published":v.get("published", "")[:10],
                    "modified": v.get("modified", "")[:10],
                    "url":      f"https://osv.dev/vulnerability/{v.get('id','')}",
                }
                for v in vulns
            ]
    except Exception:
        return []


def _extract_severity(vuln: dict) -> str:
    sev = vuln.get("database_specific", {}).get("severity", "")
    if not sev:
        for s in vuln.get("severity", []):
            if s.get("type") == "CVSS_V3":
                score = float(s.get("score", "0").split("/")[0] if "/" in s.get("score","0") else s.get("score","0"))
                if score >= 9.0:   return "CRITICAL"
                if score >= 7.0:   return "HIGH"
                if score >= 4.0:   return "MEDIUM"
                return "LOW"
    return sev or "UNKNOWN"


def _extract_cvss(vuln: dict) -> float | None:
    for s in vuln.get("severity", []):
        try:
            raw = s.get("score", "")
            if raw and isinstance(raw, (int, float)):
                return float(raw)
            if raw and "/" in raw:
                return float(raw.split("/")[0])
            if raw:
                return float(raw)
        except Exception:
            pass
    return None


@router.get("/{library_id}", response_model=ApiResponse[dict])
async def scan_library(
    library_id: int,
    force_refresh: bool = False,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """
    Scan a library for CVEs using OSV.dev.
    Results are cached; use force_refresh=true to bypass cache.
    """
    lib = await db.get(Library, library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail=f"Library {library_id} not found")

    version = lib.current_version or ""
    if not version:
        return ApiResponse.ok(
            data={"library_id": library_id, "package": lib.package, "status": "no_version",
                  "vuln_count": 0, "vulnerabilities": [], "scanned_at": None},
            meta=_meta()
        )

    # Check cache (unless force_refresh)
    if not force_refresh:
        cached = (await db.execute(
            select(CveCache)
            .where(CveCache.library_id == library_id)
            .where(CveCache.version_checked == version)
        )).scalar_one_or_none()
        if cached:
            vulns = json.loads(cached.vulns_json) if cached.vulns_json else []
            return ApiResponse.ok(
                data={
                    "library_id": library_id, "package": lib.package,
                    "sdk_name": lib.sdk_name, "platform": lib.platform,
                    "version": version, "ecosystem": cached.ecosystem,
                    "status": "cached", "vuln_count": cached.vuln_count,
                    "vulnerabilities": vulns, "scanned_at": cached.scanned_at,
                },
                meta=_meta()
            )

    # Live scan
    ecosystem = _detect_ecosystem(lib)
    vulns = await _osv_query(lib.package, ecosystem, version)

    # Upsert cache
    existing = (await db.execute(
        select(CveCache).where(CveCache.library_id == library_id)
                         .where(CveCache.version_checked == version)
    )).scalar_one_or_none()
    if existing:
        existing.vuln_count = len(vulns)
        existing.vulns_json = json.dumps(vulns)
        existing.scanned_at = _now()
    else:
        db.add(CveCache(
            library_id=library_id, ecosystem=ecosystem,
            version_checked=version, vuln_count=len(vulns),
            vulns_json=json.dumps(vulns), scanned_at=_now(),
        ))
    await db.commit()

    # Auto-escalate alert_priority if critical CVE found
    critical_count = sum(1 for v in vulns if v.get("severity") in ("CRITICAL","HIGH"))
    if critical_count > 0 and lib.alert_priority != "Critical":
        lib.alert_priority = "Critical"
        lib.updated_at = _now()
        await db.commit()

    return ApiResponse.ok(
        data={
            "library_id": library_id, "package": lib.package,
            "sdk_name": lib.sdk_name, "platform": lib.platform,
            "version": version, "ecosystem": ecosystem,
            "status": "scanned", "vuln_count": len(vulns),
            "critical_count": critical_count,
            "vulnerabilities": vulns, "scanned_at": _now(),
        },
        meta=_meta()
    )


@router.get("", response_model=ApiResponse[list[dict]])
async def list_cached_scans(
    platform: str | None = None,
    has_vulns: bool | None = None,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[dict]]:
    """Return all cached CVE scan results with library details."""
    stmt = (
        select(CveCache, Library.package, Library.sdk_name, Library.platform,
               Library.current_version, Library.update_needed, Library.status)
        .join(Library, Library.id == CveCache.library_id, isouter=True)
        .order_by(CveCache.vuln_count.desc(), CveCache.scanned_at.desc())
    )
    if platform:
        stmt = stmt.where(Library.platform == platform)
    if has_vulns is True:
        stmt = stmt.where(CveCache.vuln_count > 0)
    elif has_vulns is False:
        stmt = stmt.where(CveCache.vuln_count == 0)

    rows = (await db.execute(stmt)).all()
    data = [
        {
            "library_id":    r.CveCache.library_id,
            "package":       r.package,
            "sdk_name":      r.sdk_name,
            "platform":      r.platform,
            "version":       r.current_version,
            "update_needed": r.update_needed,
            "lib_status":    r.status,
            "ecosystem":     r.CveCache.ecosystem,
            "vuln_count":    r.CveCache.vuln_count,
            "scanned_at":    r.CveCache.scanned_at,
            "vulnerabilities": json.loads(r.CveCache.vulns_json) if r.CveCache.vulns_json else [],
        }
        for r in rows
    ]
    return ApiResponse.ok(data=data, meta=_meta())

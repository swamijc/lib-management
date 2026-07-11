"""
Router: /api/v1/libraries/{library_id}/versions
Multi-source version history: Maven Central, Google Maven, CocoaPods.
Gets release dates from POM HEAD requests and changelog URLs from POM body.
"""
from __future__ import annotations
import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models.orm import Library, LibraryVersion
from shared.models.base_schemas import ApiResponse, ResponseMeta

router = APIRouter(prefix="/api/v1/libraries", tags=["versions"])

HEADERS = {"User-Agent": "LibManagePlatform/1.0 (library-management-tool)"}
MAVEN_CENTRAL_BASE = "https://repo1.maven.org/maven2"
GOOGLE_MAVEN_BASE  = "https://dl.google.com/dl/android/maven2"
GOOGLE_MAVEN_GROUPS = (
    "androidx.", "com.google.android.", "com.google.firebase.",
    "com.google.gms.", "com.android.", "com.google.ar.",
    "com.google.maps.", "com.google.accompanist.",
)


def _meta() -> ResponseMeta:
    return ResponseMeta(service=settings.service_name, version=settings.service_version)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _parse_last_modified(header: str | None) -> str | None:
    if not header:
        return None
    try:
        t = parsedate(header)
        if t:
            return datetime(t[0], t[1], t[2]).strftime("%Y-%m-%d")
    except Exception:
        pass
    return None


def _parse_metadata_xml(xml_text: str, group: str, artifact: str, base_url: str, source: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    versions = [v.text for v in root.findall(".//version") if v.text]
    latest_in_xml = root.findtext(".//release") or root.findtext(".//latest") or ""
    group_path = group.replace(".", "/")
    results = []
    for version in versions:
        pom_url = f"{base_url}/{group_path}/{artifact}/{version}/{artifact}-{version}.pom"
        results.append({
            "version": version,
            "release_date": None,
            "release_notes": None,
            "changelog_url": None,
            "maven_url": f"https://mvnrepository.com/artifact/{group}/{artifact}/{version}",
            "pom_url": pom_url,
            "source": source,
            "is_xml_latest": (version == latest_in_xml),
        })
    return results


async def _fetch_from_base(base_url: str, group: str, artifact: str, source: str) -> list[dict]:
    group_path = group.replace(".", "/")
    url = f"{base_url}/{group_path}/{artifact}/maven-metadata.xml"
    try:
        async with httpx.AsyncClient(timeout=15.0, verify=False, headers=HEADERS) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return []
        return _parse_metadata_xml(resp.text, group, artifact, base_url, source)
    except Exception:
        return []


async def _enrich_release_dates(versions: list[dict], max_concurrent: int = 15) -> None:
    """HEAD every POM to get Last-Modified date."""
    sem = asyncio.Semaphore(max_concurrent)

    async def _one(v: dict) -> None:
        async with sem:
            try:
                async with httpx.AsyncClient(timeout=8.0, verify=False, headers=HEADERS) as client:
                    resp = await client.head(v["pom_url"])
                d = _parse_last_modified(resp.headers.get("last-modified"))
                if d:
                    v["release_date"] = d
            except Exception:
                pass

    await asyncio.gather(*[_one(v) for v in versions])


async def _enrich_pom_details(versions: list[dict], key_versions: set[str]) -> None:
    """GET POM for key versions: extract description + changelog URL."""
    sem = asyncio.Semaphore(5)

    async def _one(v: dict) -> None:
        if v["version"] not in key_versions:
            return
        async with sem:
            try:
                async with httpx.AsyncClient(timeout=10.0, verify=False, headers=HEADERS) as client:
                    resp = await client.get(v["pom_url"])
                    if resp.status_code != 200:
                        return
                root = ET.fromstring(resp.text)
                ns = {"m": "http://maven.apache.org/POM/4.0.0"}

                def _find(tag: str) -> str | None:
                    val = root.findtext(f"m:{tag}", namespaces=ns) or root.findtext(tag)
                    return val.strip() if val else None

                desc = _find("description")
                url  = _find("url")
                name = _find("name")

                if desc:
                    v["release_notes"] = desc[:600]
                if url:
                    v["changelog_url"] = url
                    # For AndroidX the pom <url> IS the release-notes page with version anchor
                    if "developer.android.com" in url or "jetpack/androidx" in url:
                        v["maven_url"] = url
                if name and not v.get("release_notes"):
                    v["release_notes"] = name
            except Exception:
                pass

    await asyncio.gather(*[_one(v) for v in versions])


async def _fetch_cocoapods_versions(pod_name: str) -> list[dict]:
    url = f"https://trunk.cocoapods.org/api/v1/pods/{pod_name}"
    try:
        async with httpx.AsyncClient(timeout=15.0, verify=False, headers=HEADERS) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        data = resp.json()
        results = []
        for v in data.get("versions", []):
            ver = v.get("name", "")
            results.append({
                "version": ver,
                "release_date": (v.get("created_at") or "")[:10] or None,
                "release_notes": None,
                "changelog_url": f"https://cocoapods.org/pods/{pod_name}",
                "maven_url": f"https://cocoapods.org/pods/{pod_name}",
                "pom_url": None,
                "source": "cocoapods",
                "is_xml_latest": False,
            })
        return results
    except Exception:
        return []


async def _do_fetch_versions(library_id: int, db: AsyncSession) -> dict:
    lib = await db.get(Library, library_id)
    if lib is None:
        return {"error": f"Library {library_id} not found"}
    if (lib.status or "").strip().lower() == "inactive":
        return {"stored": 0, "total_found": 0, "source": "none", "error": "Library is inactive; fetch skipped"}

    package  = lib.package or ""
    registry = (lib.registry or "").lower()
    platform = (lib.platform or "").lower()

    raw: list[dict] = []
    source_used = "none"
    error: str | None = None

    if registry == "custom" and lib.repo_url:
        # HTML release-notes page (e.g. OPPWa docs) — parse version headings
        import re as _re
        _ver_re = _re.compile(
            r"(?:#{1,4}\s+Version\s+|Version\s+)([\d]+\.[\d]+(?:\.[\d]+)*)",
            _re.IGNORECASE,
        )
        try:
            async with httpx.AsyncClient(timeout=20.0) as _client:
                _resp = await _client.get(
                    lib.repo_url,
                    follow_redirects=True,
                    headers={"User-Agent": "LibManagement-Scraper/1.0"},
                )
            _resp.raise_for_status()
            _seen: set[str] = set()
            for _m in _ver_re.finditer(_resp.text):
                _v = _m.group(1).strip()
                if _v not in _seen:
                    _seen.add(_v)
                    raw.append({"version": _v, "release_notes": None, "release_date": None})
            source_used = "html_release_notes"
        except Exception as _exc:
            error = f"HTML version fetch failed for '{lib.repo_url}': {_exc}"
    elif ":" in package:
        group, artifact = package.split(":", 1)
        is_google = group.lower().startswith(GOOGLE_MAVEN_GROUPS)
        order = (
            [(GOOGLE_MAVEN_BASE, "google_maven"), (MAVEN_CENTRAL_BASE, "maven_central")]
            if is_google else
            [(MAVEN_CENTRAL_BASE, "maven_central"), (GOOGLE_MAVEN_BASE, "google_maven")]
        )
        for base, src in order:
            versions = await _fetch_from_base(base, group, artifact, src)
            if versions:
                raw = versions
                source_used = src
                break
        if not raw:
            error = f"'{package}' not found on Maven Central or Google Maven"

        if raw:
            latest_ver  = lib.latest_version or ""
            current_ver = lib.current_version or ""

            # Step 1: release dates via HEAD (all versions, parallel)
            await _enrich_release_dates(raw)

            # Step 2: POM details for current + latest + 5 most-recent
            sorted_by_date = sorted(
                [v for v in raw if v.get("release_date")],
                key=lambda x: x["release_date"] or "", reverse=True,
            )
            key_vers = (
                {latest_ver, current_ver}
                | {v["version"] for v in sorted_by_date[:5]}
            )
            await _enrich_pom_details(raw, key_vers)

    elif "cocoapods" in registry or "ios" in platform:
        raw = await _fetch_cocoapods_versions(package)
        source_used = "cocoapods"
        if not raw:
            error = f"CocoaPods package '{package}' not found"
    else:
        error = f"No version fetcher for '{package}' (registry={registry}, platform={platform})"

    if not raw:
        return {"stored": 0, "total_found": 0, "source": source_used, "error": error}

    latest_ver  = lib.latest_version or ""
    current_ver = lib.current_version or ""
    stored = 0

    for v in raw:
        version_str = v.get("version", "")
        if not version_str:
            continue
        existing = (await db.execute(
            select(LibraryVersion).where(
                LibraryVersion.library_id == library_id,
                LibraryVersion.version == version_str,
            )
        )).scalar_one_or_none()

        is_latest  = (version_str == latest_ver)
        is_current = (version_str == current_ver)

        if existing:
            if v.get("release_date"):
                existing.release_date = v["release_date"]
            if v.get("release_notes"):
                existing.release_notes = v["release_notes"]
            if v.get("maven_url"):
                existing.maven_url = v["maven_url"]
            existing.pom_url   = v.get("changelog_url") or v.get("pom_url") or existing.pom_url
            existing.is_latest  = is_latest
            existing.is_current = is_current
            existing.scraped_at = _now()
        else:
            db.add(LibraryVersion(
                library_id=library_id,
                version=version_str,
                release_date=v.get("release_date"),
                release_notes=v.get("release_notes"),
                maven_url=v.get("maven_url"),
                pom_url=v.get("changelog_url") or v.get("pom_url"),
                is_latest=is_latest,
                is_current=is_current,
                scraped_at=_now(),
            ))
        stored += 1

    await db.commit()
    return {"stored": stored, "total_found": len(raw), "source": source_used, "error": error, "package": package}


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/{library_id}/versions", response_model=ApiResponse[dict])
async def list_versions(library_id: int, db: AsyncSession = Depends(get_db)) -> ApiResponse[dict]:
    lib = await db.get(Library, library_id)
    if lib is None:
        raise HTTPException(status_code=404, detail=f"Library {library_id} not found")
    rows = (await db.execute(
        select(LibraryVersion)
        .where(LibraryVersion.library_id == library_id)
        .order_by(LibraryVersion.release_date.desc(), LibraryVersion.id.desc())
    )).scalars().all()
    return ApiResponse.ok(
        data={
            "library_id": library_id,
            "package": lib.package,
            "sdk_name": lib.sdk_name,
            "platform": lib.platform,
            "registry": lib.registry,
            "current_version": lib.current_version,
            "latest_version": lib.latest_version,
            "total": len(rows),
            "versions": [
                {
                    "id": r.id, "version": r.version,
                    "release_date": r.release_date,
                    "release_notes": r.release_notes,
                    "maven_url": r.maven_url,
                    "changelog_url": r.pom_url,
                    "is_latest": r.is_latest,
                    "is_current": r.is_current,
                    "scraped_at": r.scraped_at,
                }
                for r in rows
            ],
        },
        meta=_meta(),
    )


@router.post("/{library_id}/fetch-versions", response_model=ApiResponse[dict])
async def fetch_versions(library_id: int, db: AsyncSession = Depends(get_db)) -> ApiResponse[dict]:
    """Fetch all versions + release dates + changelog URLs from Maven Central / Google Maven / CocoaPods."""
    result = await _do_fetch_versions(library_id, db)
    if result.get("error") and not result.get("stored"):
        raise HTTPException(status_code=422, detail=result["error"])
    return ApiResponse.ok(data=result, meta=_meta())


# ── Bulk operations ───────────────────────────────────────────────────────────

@router.post("/sync-maven-urls", response_model=ApiResponse[dict])
async def sync_maven_urls(db: AsyncSession = Depends(get_db)) -> ApiResponse[dict]:
    """
    Set repo_url = https://mvnrepository.com/artifact/{group}/{artifact}
    for every library whose package is in groupId:artifactId format.
    """
    rows = (await db.execute(select(Library))).scalars().all()
    updated = 0
    skipped = 0
    for lib in rows:
        pkg = lib.package or ""
        if ":" not in pkg or pkg.startswith("http"):
            skipped += 1
            continue
        group, artifact = pkg.split(":", 1)
        correct_url = f"https://mvnrepository.com/artifact/{group}/{artifact}"
        if lib.repo_url != correct_url:
            lib.repo_url = correct_url
            updated += 1
    await db.commit()
    return ApiResponse.ok(
        data={"updated": updated, "skipped": skipped, "total": len(rows)},
        meta=_meta(),
    )


# simple in-memory bulk job state
_bulk_status: dict = {"running": False, "done": 0, "total": 0, "errors": 0, "last_run": None}


async def _run_bulk_fetch_bg(library_ids: list[int]) -> None:
    """Run bulk version fetch in background."""
    global _bulk_status
    _bulk_status.update({"running": True, "done": 0, "total": len(library_ids), "errors": 0})
    sem = asyncio.Semaphore(4)

    async def _one(lib_id: int) -> None:
        async with sem:
            from ..database import AsyncSessionLocal  # local import
            try:
                async with AsyncSessionLocal() as session:
                    result = await _do_fetch_versions(lib_id, session)
                    if result.get("stored", 0) > 0:
                        _bulk_status["done"] += 1
                    else:
                        _bulk_status["errors"] += 1
            except Exception:
                _bulk_status["errors"] += 1

    await asyncio.gather(*[_one(lid) for lid in library_ids])
    _bulk_status.update({"running": False, "last_run": _now()})


@router.post("/bulk-fetch-versions", response_model=ApiResponse[dict])
async def bulk_fetch_versions(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """Trigger version history fetch for ALL Android/Maven libraries (background job)."""
    if _bulk_status.get("running"):
        return ApiResponse.ok(data={"message": "Already running", **_bulk_status}, meta=_meta())

    rows = (await db.execute(
        select(Library.id, Library.package, Library.status)
    )).all()
    eligible = [
        r.id for r in rows
        if (r.status or "").strip().lower() != "inactive"
        and ":" in (r.package or "")
        and not (r.package or "").startswith("http")
    ]
    background_tasks.add_task(_run_bulk_fetch_bg, eligible)
    return ApiResponse.ok(
        data={"message": f"Bulk fetch started for {len(eligible)} libraries", "total": len(eligible)},
        meta=_meta(),
    )


@router.get("/bulk-fetch-versions/status", response_model=ApiResponse[dict])
async def bulk_fetch_status() -> ApiResponse[dict]:
    """Poll the bulk fetch job status."""
    return ApiResponse.ok(data=_bulk_status, meta=_meta())

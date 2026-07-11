"""
Comparison Service — version comparison engine.

Uses `packaging.version.Version` for semver-style parsing (same library used by
pip). Falls back to the shared `normalise_version()` utility for non-semver
strings (e.g. '55.0(internal)', 'ViaSPM', date-based versions).
"""
from __future__ import annotations

from packaging.version import Version, InvalidVersion

from shared.utils.version_parser import normalise_version
from ..models.schemas import ComparisonResult, VersionStatus


def compare_versions(
    library_id: int,
    package: str,
    platform: str,
    current_version: str,
    latest_version: str,
    update_needed: str | None = None,
    library_status: str | None = None,
) -> ComparisonResult:
    """
    Compare `current_version` against `latest_version` and return a
    ComparisonResult capturing the delta.

    Priority order:
      1. packaging.version.Version (strict semver / PEP 440)
      2. normalise_version() from shared utils (handles dates, internal markers)
      3. Mark as needs_manual_review if both fail
    """
    # ── Try strict semver parse first ────────────────────────────────────────
    try:
        current_v = Version(current_version)
        latest_v = Version(latest_version)
        return _build_result_from_packaging(
            library_id, package, platform,
            current_version, latest_version,
            current_v, latest_v,
            update_needed, library_status,
        )
    except InvalidVersion:
        pass

    # ── Fall back to normalise_version ───────────────────────────────────────
    norm_current, strat_current = normalise_version(current_version)
    norm_latest, strat_latest = normalise_version(latest_version)

    if norm_current is not None and norm_latest is not None:
        return _build_result_from_packaging(
            library_id, package, platform,
            current_version, latest_version,
            norm_current, norm_latest,
            update_needed, library_status,
        )

    # ── String equality fallback ──────────────────────────────────────────────
    if current_version.strip() == latest_version.strip():
        version_status = VersionStatus.SAME
        new_version = False
    else:
        # Can't determine ordering; flag for manual review
        version_status = VersionStatus.UNKNOWN
        new_version = False

    return ComparisonResult(
        library_id=library_id,
        package=package,
        platform=platform,
        current_version=current_version,
        latest_version=latest_version,
        version_status=version_status,
        new_version_released=new_version,
        needs_manual_review=True,
        update_needed=update_needed,
        library_status=library_status,
    )


# ── Internal helper ───────────────────────────────────────────────────────────

def _build_result_from_packaging(
    library_id: int,
    package: str,
    platform: str,
    current_raw: str,
    latest_raw: str,
    current_v: Version,
    latest_v: Version,
    update_needed: str | None,
    library_status: str | None,
) -> ComparisonResult:
    if latest_v > current_v:
        status = VersionStatus.NEWER
        new_version = True
    elif latest_v == current_v:
        status = VersionStatus.SAME
        new_version = False
    else:
        status = VersionStatus.OLDER
        new_version = False

    # Bump classification (only meaningful when newer)
    major_bump = minor_bump = patch_bump = False
    if status == VersionStatus.NEWER:
        if latest_v.major > current_v.major:
            major_bump = True
        elif latest_v.minor > current_v.minor:
            minor_bump = True
        else:
            patch_bump = True

    return ComparisonResult(
        library_id=library_id,
        package=package,
        platform=platform,
        current_version=current_raw,
        latest_version=latest_raw,
        version_status=status,
        new_version_released=new_version,
        major_bump=major_bump,
        minor_bump=minor_bump,
        patch_bump=patch_bump,
        update_needed=update_needed,
        library_status=library_status,
    )

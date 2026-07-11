"""
Semantic version normaliser — handles all non-standard version strings
found in the existing library DB (T4 gap from architecture document).

Strategies (tried in order):
  1. 'semver'    — direct packaging.version.Version parse
  2. 'extracted' — regex extract first numeric block (e.g. "core-v7.1.7" → "7.1.7")
  3. 'date'      — YYYYMM.x.y.z numeric comparison
  4. 'unknown'   — unparseable; returns None → triggers 'manual_review' in UI

Known problematic versions pre-seeded in DB:
  core-v7.1.7         → extracted → 7.1.7
  202407.1.0.0        → date      → comparable as float tuple
  NotinPodfile.lock   → unknown
  ViaSPM              → unknown
  55.0(internal)      → extracted → 55.0
"""
from __future__ import annotations
import re
from typing import Literal
from packaging.version import Version, InvalidVersion

VersionStrategy = Literal["semver", "extracted", "date", "unknown"]

# Strings that are placeholder text, not real versions
_PLACEHOLDER_VERSIONS = frozenset({
    "viaspm", "notinpodfile.lock", "n/a", "unknown", "—", "-", "",
    "none", "null", "tbd",
})


def normalise_version(raw: str | None) -> tuple[Version | None, VersionStrategy]:
    """
    Parse a raw version string into a packaging.Version.

    Returns:
        (parsed_version, strategy_used)
        parsed_version is None when strategy == 'unknown'.

    Examples:
        >>> normalise_version("3.18.0")
        (Version("3.18.0"), "semver")
        >>> normalise_version("core-v7.1.7")
        (Version("7.1.7"), "extracted")
        >>> normalise_version("ViaSPM")
        (None, "unknown")
    """
    if raw is None:
        return None, "unknown"

    cleaned = raw.strip()

    # ── Placeholder / non-version text ──────────────────────────────────────
    if cleaned.lower() in _PLACEHOLDER_VERSIONS:
        return None, "unknown"

    # ── Strip internal markers like "55.0(internal)" ────────────────────────
    cleaned = re.sub(r"\(.*?\)", "", cleaned).strip()

    # ── Strategy 1: Direct semver parse ────────────────────────────────────
    try:
        return Version(cleaned), "semver"
    except InvalidVersion:
        pass

    # ── Strategy 2: Extract first numeric version block ────────────────────
    # Handles: "core-v7.1.7" → "7.1.7", "sdk-bom-3.18.0" → "3.18.0"
    match = re.search(r"(\d+\.\d+(?:\.\d+)*)", cleaned)
    if match:
        try:
            return Version(match.group(1)), "extracted"
        except InvalidVersion:
            pass

    # ── Strategy 3: Date-based versions like "202407.1.0.0" ────────────────
    # Treat as tuple of ints for comparison — convert to semver-ish
    date_match = re.fullmatch(r"(\d{6})\.(\d+)\.(\d+)(?:\.(\d+))?", cleaned)
    if date_match:
        parts = [g for g in date_match.groups() if g is not None]
        synthetic = ".".join(parts)
        try:
            return Version(synthetic), "date"
        except InvalidVersion:
            pass

    return None, "unknown"


def compare_versions(current_raw: str | None, latest_raw: str | None) -> Literal["newer", "same", "older", "unknown"]:
    """
    Compare two raw version strings.

    Returns:
        'newer'   — latest > current  (new release available)
        'same'    — latest == current (up to date)
        'older'   — latest < current  (unusual; current is ahead)
        'unknown' — either version could not be parsed
    """
    current, _ = normalise_version(current_raw)
    latest, _ = normalise_version(latest_raw)

    if current is None or latest is None:
        return "unknown"

    if latest > current:
        return "newer"
    if latest == current:
        return "same"
    return "older"

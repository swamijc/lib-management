"""
SDK Update Priority Classification — Team-defined 4-tier logic.

Priority: CRITICAL > HIGH > MODERATE > LOW > UP_TO_DATE

Rule 1 — Version diff:
  MAJOR bump  → CRITICAL
  MINOR bump  → HIGH
  PATCH bump  → MODERATE
  Same        → UP_TO_DATE

Rule 2 — Keyword scan of release notes (take highest match)
Rule 3 — Merge: always take the HIGHER of version + keyword priority
Rule 4 — SDK sensitivity: per-SDK minimum floor
"""
from __future__ import annotations
from packaging.version import Version, InvalidVersion

# ── Priority ladder (index = severity) ───────────────────────────────────────
PRIORITY_ORDER = ["LOW", "MODERATE", "HIGH", "CRITICAL"]

# ── Keyword → Priority rules ─────────────────────────────────────────────────
KEYWORD_RULES: dict[str, list[str]] = {
    "CRITICAL": [
        "critical", "urgent", "emergency", "zero-day",
        "remote code execution", "rce", "actively exploited",
        "must update", "immediate action", "breaking change",
        "incompatible", "data breach", "vulnerability", "cve",
    ],
    "HIGH": [
        "security fix", "security patch", "security update",
        "authentication", "authorization", "payment", "pci", "gdpr",
        "compliance", "crash fix", "memory leak", "data loss",
        "important", "regression", "breaking", "deprecated",
        "end of life", "eol", "3ds", "sdk mandatory", "force update",
    ],
    "MODERATE": [
        "bug fix", "bugfix", "fixed", "improvement", "performance",
        "stability", "enhancement", "updated dependency",
        "dependency update", "api change", "behaviour change",
        "behavior change", "recommended",
    ],
    "LOW": [
        "minor", "cosmetic", "typo", "documentation", "readme",
        "refactor", "cleanup", "ui update", "log improvement",
        "optional", "new feature", "added support",
    ],
}

# ── SDK-specific minimum priority floors ──────────────────────────────────────
SDK_SENSITIVITY: dict[str, str] = {
    # Payment SDKs — any update treated minimum HIGH
    "ACI":                  "HIGH",
    "ACI IPWorks":          "HIGH",
    "ACI OPPWa":            "HIGH",
    "ACI - ipworks3ds_sdk": "HIGH",
    "ACI - OPPWAMobile":    "HIGH",
    "Braintree":            "HIGH",
    "PayPal":               "HIGH",
    "KlarnaMobileSDK":      "HIGH",
    "Klarna":               "HIGH",
    # Auth / Identity SDKs
    "Gigya":                "HIGH",
    "GigyaAuth":            "HIGH",
    "GigyaTfa":             "HIGH",
    # Security
    "SQLCipher":            "HIGH",
    # Analytics / Telemetry
    "Firebase":             "MODERATE",
    "FirebaseCrashlytics":  "MODERATE",
    "FirebasePerformance":  "MODERATE",
    "FirebaseRemoteConfig": "MODERATE",
    "AppsFlyer":            "MODERATE",
    "ContentsquareSDK":     "MODERATE",
    "BlueTriangleSDK-Swift":"MODERATE",
    "BlueTriangle SDK":     "MODERATE",
    # Standard networking / UI — LOW baseline
    "Alamofire":            "LOW",
    "AFNetworking":         "LOW",
    "Glide":                "LOW",
    "SDWebImage":           "LOW",
    "lottie-ios":           "LOW",
    "Lottie for Android":   "LOW",
    "Mantle":               "LOW",
    "Retrofit":             "LOW",
    "OkHttp":               "LOW",
    "RecyclerView":         "LOW",
    "WorkManager":          "LOW",
}


def merge_priority(a: str, b: str) -> str:
    """Return the higher of two priority strings."""
    ia = PRIORITY_ORDER.index(a) if a in PRIORITY_ORDER else 0
    ib = PRIORITY_ORDER.index(b) if b in PRIORITY_ORDER else 0
    return PRIORITY_ORDER[max(ia, ib)]


def classify_by_version(current: str, latest: str) -> str:
    """
    MAJOR bump → CRITICAL
    MINOR bump → HIGH
    PATCH bump → MODERATE
    Same       → UP_TO_DATE
    """
    try:
        cv, lv = Version(current), Version(latest)
        if lv.major > cv.major:    return "CRITICAL"
        elif lv.minor > cv.minor:  return "HIGH"
        elif lv.micro > cv.micro:  return "MODERATE"
        else:                      return "UP_TO_DATE"
    except InvalidVersion:
        if not current or not latest:
            return "UP_TO_DATE"
        return "UP_TO_DATE" if current.strip() == latest.strip() else "MODERATE"


def scan_keywords(release_notes: str) -> tuple[str, list[tuple[str, str]]]:
    """
    Scan release notes for priority keywords.
    Returns (keyword_priority, list_of_(keyword, priority) matches).
    """
    if not release_notes:
        return "LOW", []
    text = release_notes.lower()
    matched: list[tuple[str, str]] = []
    kw_priority = "LOW"
    for priority in ["CRITICAL", "HIGH", "MODERATE", "LOW"]:
        for keyword in KEYWORD_RULES[priority]:
            if keyword.lower() in text:
                matched.append((keyword, priority))
                kw_priority = merge_priority(kw_priority, priority)
    return kw_priority, matched


def apply_sdk_sensitivity(sdk_name: str, current_priority: str) -> str:
    """Apply per-SDK minimum priority floor."""
    if not sdk_name:
        return current_priority
    # Exact match first
    baseline = SDK_SENSITIVITY.get(sdk_name)
    if baseline is None:
        # Prefix / substring match
        sdk_lower = sdk_name.lower()
        for key, val in SDK_SENSITIVITY.items():
            if key.lower() in sdk_lower or sdk_lower in key.lower():
                baseline = val
                break
    if baseline is None:
        baseline = "LOW"
    return merge_priority(baseline, current_priority)


def classify_update(
    sdk_name: str,
    current_version: str,
    latest_version: str,
    release_notes: str = "",
) -> dict:
    """
    Full classification:
      version diff + keyword scan + SDK sensitivity → CRITICAL/HIGH/MODERATE/LOW/UP_TO_DATE

    Returns a dict with 'priority', 'reason', 'version_priority',
    'keyword_priority', 'matched_keywords'.
    """
    # Rule 1 — version diff
    version_priority = classify_by_version(current_version, latest_version)

    if version_priority == "UP_TO_DATE":
        return {
            "priority":         "UP_TO_DATE",
            "version_priority": "UP_TO_DATE",
            "keyword_priority": "LOW",
            "matched_keywords": [],
            "reason":           "Already on latest version",
        }

    # Rule 2 — keyword scan
    keyword_priority, matched_keywords = scan_keywords(release_notes)

    # Rule 3 — merge (take higher)
    merged_priority = merge_priority(version_priority, keyword_priority)

    # Rule 4 — SDK sensitivity floor
    final_priority = apply_sdk_sensitivity(sdk_name, merged_priority)

    # Build reason string
    if matched_keywords:
        top = [kw for kw, _ in matched_keywords[:3]]
        reason = f"Release notes contain: {', '.join(top)}. Priority: {final_priority}"
    else:
        reason = f"Version bump ({version_priority}). Priority: {final_priority}"

    return {
        "priority":         final_priority,
        "version_priority": version_priority,
        "keyword_priority": keyword_priority,
        "matched_keywords": matched_keywords,
        "reason":           reason,
    }


def priority_to_update_needed(priority: str) -> str:
    """Map 4-tier priority to DB update_needed value (lowercase)."""
    return {
        "CRITICAL":   "critical",
        "HIGH":       "high",
        "MODERATE":   "moderate",
        "LOW":        "low",
        "UP_TO_DATE": "none",
    }.get(priority, "none")

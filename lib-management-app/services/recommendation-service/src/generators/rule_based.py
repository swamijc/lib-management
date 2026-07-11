"""
Rule-based recommendation generator — implements team's 4-tier priority logic.

Priority: CRITICAL > HIGH > MODERATE > LOW > UP_TO_DATE

Rule 1 — Version diff (MAJOR→CRITICAL, MINOR→HIGH, PATCH→MODERATE)
Rule 2 — Keyword scan of release notes
Rule 3 — Merge: always take HIGHER priority
Rule 4 — SDK sensitivity: per-SDK minimum floor

Config source: priority_rules_config in app_settings DB (via library-data-service).
Falls back to hardcoded defaults if the settings API is unavailable.
"""
from __future__ import annotations
import json
import time
import logging

import httpx
from packaging.version import Version, InvalidVersion

from ..config import settings as _app_settings
from ..models.schemas import (
    GeneratorType,
    RecommendationRequest,
    RecommendationResult,
    UpgradeDecision,
)
from .base import RecommendationGenerator

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# ── Hardcoded defaults (used as fallback if DB config unavailable) ────────────
# ══════════════════════════════════════════════════════════════════════════════

_PRIORITY_ORDER = ["LOW", "MODERATE", "HIGH", "CRITICAL"]

_DEFAULT_KEYWORD_RULES: dict[str, list[str]] = {
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

_DEFAULT_SDK_SENSITIVITY: dict[str, str] = {
    "ACI": "HIGH", "ACI IPWorks": "HIGH", "ACI OPPWa": "HIGH",
    "ACI - ipworks3ds_sdk": "HIGH", "ACI - OPPWAMobile": "HIGH",
    "Braintree": "HIGH", "PayPal": "HIGH",
    "KlarnaMobileSDK": "HIGH", "Klarna": "HIGH",
    "Gigya": "HIGH", "GigyaAuth": "HIGH", "GigyaTfa": "HIGH",
    "SQLCipher": "HIGH",
    "Firebase": "MODERATE", "FirebaseCrashlytics": "MODERATE",
    "FirebasePerformance": "MODERATE", "FirebaseRemoteConfig": "MODERATE",
    "AppsFlyer": "MODERATE", "ContentsquareSDK": "MODERATE",
    "BlueTriangleSDK-Swift": "MODERATE", "BlueTriangle SDK": "MODERATE",
    "Alamofire": "LOW", "AFNetworking": "LOW", "Glide": "LOW",
    "SDWebImage": "LOW", "lottie-ios": "LOW", "Mantle": "LOW",
}

# ── DB config cache (5-minute TTL) ────────────────────────────────────────────
_CONFIG_CACHE: dict = {}
_CONFIG_CACHE_TIME: float = 0.0
_CONFIG_TTL: float = 300.0   # seconds


def _load_config_from_db() -> dict | None:
    """Fetch priority_rules_config from library-data-service settings.
    Returns the parsed config dict or None if unavailable."""
    global _CONFIG_CACHE, _CONFIG_CACHE_TIME
    now = time.monotonic()
    if _CONFIG_CACHE and (now - _CONFIG_CACHE_TIME) < _CONFIG_TTL:
        return _CONFIG_CACHE
    try:
        url = f"{_app_settings.library_data_service_url}/api/v1/settings/app"
        headers = {"X-Internal-Service-Key": _app_settings.internal_service_key}
        with httpx.Client(timeout=4.0) as client:
            resp = client.get(url, headers=headers)
        if resp.status_code == 200:
            items = resp.json().get("data", []) or []
            for item in items:
                if item.get("key") == "priority_rules_config":
                    raw = item.get("value", "")
                    cfg = json.loads(raw) if isinstance(raw, str) else raw
                    if isinstance(cfg, dict) and cfg.get("keywords"):
                        _CONFIG_CACHE = cfg
                        _CONFIG_CACHE_TIME = now
                        logger.debug("priority_rules loaded from DB settings")
                        return cfg
    except Exception as exc:
        logger.warning("Could not load priority_rules from DB: %s — using defaults", exc)
    return None


def _get_keyword_rules() -> dict[str, list[str]]:
    """Return keyword rules: from DB settings if available, else hardcoded defaults."""
    cfg = _load_config_from_db()
    kw = (cfg or {}).get("keywords", {})
    if kw and all(tier in kw for tier in ["CRITICAL", "HIGH", "MODERATE", "LOW"]):
        return {tier: [str(k).lower() for k in kw[tier]] for tier in kw}
    return _DEFAULT_KEYWORD_RULES


def _get_sdk_sensitivity() -> dict[str, str]:
    """Return SDK sensitivity map: from DB settings if available, else hardcoded defaults."""
    cfg = _load_config_from_db()
    floors = (cfg or {}).get("sdk_floors", [])
    if floors:
        return {entry["sdk"]: entry["floor"] for entry in floors if "sdk" in entry and "floor" in entry}
    return _DEFAULT_SDK_SENSITIVITY


def invalidate_config_cache() -> None:
    """Force reload of config on next request (e.g. after settings change)."""
    global _CONFIG_CACHE_TIME
    _CONFIG_CACHE_TIME = 0.0

_PROS: dict[str, list[str]] = {
    "CRITICAL": ["Fixes critical security/breaking change", "Required for compliance", "Platform support continuity"],
    "HIGH":     ["Fixes security or payment-related issue", "Resolves significant crash/data risk"],
    "MODERATE": ["Includes bug fixes and performance improvements", "Keeps dependency graph current"],
    "LOW":      ["Minor improvements and cleanups", "Keeps library up to date"],
}
_CONS: dict[str, list[str]] = {
    "CRITICAL": ["Requires immediate testing and deployment"],
    "HIGH":     ["Regression testing required", "Possible minor API changes"],
    "MODERATE": ["Test suite should be run after upgrade"],
    "LOW":      ["Low risk but some testing advisable"],
}


def _merge(a: str, b: str) -> str:
    ia = _PRIORITY_ORDER.index(a) if a in _PRIORITY_ORDER else 0
    ib = _PRIORITY_ORDER.index(b) if b in _PRIORITY_ORDER else 0
    return _PRIORITY_ORDER[max(ia, ib)]


def _version_priority(cur: str, lat: str) -> str:
    try:
        cv, lv = Version(cur), Version(lat)
        if lv.major > cv.major:    return "CRITICAL"
        elif lv.minor > cv.minor:  return "HIGH"
        elif lv.micro > cv.micro:  return "MODERATE"
        else:                      return "UP_TO_DATE"
    except InvalidVersion:
        return "UP_TO_DATE" if not cur or not lat or cur.strip() == lat.strip() else "MODERATE"


def _keyword_priority(notes: str) -> tuple[str, list[tuple[str, str]]]:
    if not notes:
        return "LOW", []
    text = notes.lower()
    matched: list[tuple[str, str]] = []
    kp = "LOW"
    keyword_rules = _get_keyword_rules()   # reads from DB config or defaults
    for pri in ["CRITICAL", "HIGH", "MODERATE", "LOW"]:
        for kw in keyword_rules.get(pri, []):
            if kw.lower() in text:
                matched.append((kw, pri))
                kp = _merge(kp, pri)
    return kp, matched


def _sdk_floor(sdk: str, pri: str) -> str:
    sdk_sensitivity = _get_sdk_sensitivity()   # reads from DB config or defaults
    baseline = sdk_sensitivity.get(sdk or "")
    if baseline is None:
        sdk_l = (sdk or "").lower()
        for key, val in sdk_sensitivity.items():
            if key.lower() in sdk_l or sdk_l in key.lower():
                baseline = val
                break
    return _merge(baseline or "LOW", pri)


_BUMP_LABEL: dict[str, str] = {
    "CRITICAL": "major", "HIGH": "minor", "MODERATE": "patch", "LOW": "patch",
}


def classify_update(sdk: str, cur: str, lat: str, notes: str = "") -> dict:
    vp = _version_priority(cur, lat)
    if vp == "UP_TO_DATE":
        return {"priority": "UP_TO_DATE", "version_priority": vp,
                "keyword_priority": "LOW", "matched_keywords": [],
                "reason": f"Already on latest version ({cur})"}
    kp, matched = _keyword_priority(notes)
    merged  = _merge(vp, kp)
    final   = _sdk_floor(sdk, merged)
    top_kw  = [kw for kw, _ in matched[:3]]
    bump    = _BUMP_LABEL.get(vp, vp.lower())
    if top_kw:
        reason = (f"{cur} \u2192 {lat} ({bump} bump) — release notes: {', '.join(top_kw)}. Priority: {final}")
    else:
        reason = f"{cur} \u2192 {lat} ({bump} version bump). Priority: {final}"
    return {"priority": final, "version_priority": vp,
            "keyword_priority": kp, "matched_keywords": matched, "reason": reason}


class RuleBasedGenerator(RecommendationGenerator):

    @property
    def generator_type(self) -> str:
        return GeneratorType.RULE_BASED

    async def generate(self, req: RecommendationRequest) -> RecommendationResult:
        priority, decision, summary, up_pros, up_cons, no_pros, no_cons = self._apply_rules(req)
        return RecommendationResult(
            library_id=req.library_id,
            package=req.package,
            platform=req.platform,
            current_version=req.current_version,
            latest_version=req.latest_version,
            priority=priority,
            upgrade_recommended=decision,
            upgrade_pros=up_pros,
            upgrade_cons=up_cons,
            no_upgrade_pros=no_pros,
            no_upgrade_cons=no_cons,
            recommendation_summary=summary,
            generator_used=GeneratorType.RULE_BASED,
        )

    def _apply_rules(self, req: RecommendationRequest):
        pkg       = req.package or ""
        cur       = req.current_version or ""
        lat       = req.latest_version or ""
        status    = (req.library_status or "").lower()
        dep_notes = req.deprecation_notes or ""

        # Rule 1: Deprecated — always force upgrade
        if status == "deprecated":
            return ("CRITICAL", UpgradeDecision.YES,
                    f"[CRITICAL] {pkg} is deprecated — migration away from this library is required.",
                    ["Eliminates use of unsupported / unmaintained library", "Reduces security risk",
                     dep_notes[:120] if dep_notes else "Replacement available"],
                    ["Migration effort required"],
                    ["No immediate break if deferred"],
                    ["Continued use increases tech debt"])

        # Rule 2: Unparseable version — manual review
        if req.needs_manual_review:
            return ("MANUAL_REVIEW", UpgradeDecision.NO,
                    f"{pkg}: version '{cur}' is non-standard. Manual review required.",
                    [], [], [],
                    ["Non-standard version — automated comparison unreliable"])

        # Rule 3: Already up to date
        if not req.new_version_released or cur.strip() == lat.strip():
            return ("NONE", UpgradeDecision.SUFFICIENT,
                    f"{pkg} is up-to-date at version {cur}. No upgrade needed.",
                    [], [],
                    ["Library is at the latest version"],
                    [])

        # Rule 4: 4-tier classification
        result   = classify_update(sdk=pkg, cur=cur, lat=lat, notes=req.release_notes or "")
        priority = result["priority"]

        if priority == "UP_TO_DATE":
            return ("NONE", UpgradeDecision.SUFFICIENT,
                    f"{pkg} is up-to-date at version {cur}.",
                    [], [],
                    ["Library is at the latest version"],
                    [])

        decision = UpgradeDecision.YES if priority in ("CRITICAL","HIGH","MODERATE") else UpgradeDecision.NO
        summary  = f"[{priority}] {pkg}: {result['reason']}"

        up_pros  = list(_PROS.get(priority, ["Upgrade available"]))
        up_cons  = list(_CONS.get(priority, ["Testing required"]))
        no_pros  = ["Avoids disruption if upgrade is not urgent"]
        no_cons  = [f"Staying on {cur} risks security and stability debt"]

        matched = result.get("matched_keywords", [])
        if matched:
            kws = [kw for kw, _ in matched[:3]]
            up_pros = [f"Keywords in release notes: {', '.join(kws)}"] + up_pros

        return priority, decision, summary, up_pros, up_cons, no_pros, no_cons

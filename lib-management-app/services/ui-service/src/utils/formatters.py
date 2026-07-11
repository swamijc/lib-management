"""Pure display-formatting helpers — no Streamlit dependency."""
from __future__ import annotations
from datetime import datetime

_STATUS_ICONS: dict[str, str] = {
    "up_to_date":    "✅",
    "patch_update":  "🔵",
    "minor_update":  "🟡",
    "major_update":  "🔴",
    "unknown":       "❓",
}

_DECISION_ICONS: dict[str, str] = {
    "upgrade": "⬆️",
    "hold":    "⏸️",
    "review":  "🔍",
    "none":    "—",
}

_REGISTRY_LABELS: dict[str, str] = {
    "maven":       "☕ Maven",
    "cocoapods":   "🍎 CocoaPods",
    "spm":         "🍎 Swift PM",
    "github":      "🐙 GitHub",
    "custom_http": "🌐 Custom HTTP",
}


def format_version_status(status: str) -> str:
    """Return icon + human label for a VersionStatus string."""
    icon = _STATUS_ICONS.get(status, "❓")
    label = status.replace("_", " ").title()
    return f"{icon} {label}"


def format_upgrade_decision(decision: str | None) -> str:
    """Return icon + label for an upgrade decision, or '—' for None."""
    if decision is None:
        return "—"
    icon = _DECISION_ICONS.get(decision, "")
    label = decision.replace("_", " ").title()
    return f"{icon} {label}".strip()


def format_datetime(value: str | datetime | None) -> str:
    """Return a UTC timestamp string, or '—' for None / unparseable."""
    if value is None:
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    return value.strftime("%Y-%m-%d %H:%M UTC")


def format_registry(registry: str | None) -> str:
    """Return emoji-prefixed registry label, or raw string if unknown."""
    if not registry:
        return "—"
    return _REGISTRY_LABELS.get(registry, registry)


def format_pipeline_status(status: str) -> str:
    """Return coloured indicator for pipeline run status."""
    mapping = {
        "running":   "🔄 Running",
        "completed": "✅ Completed",
        "failed":    "❌ Failed",
        "pending":   "⏳ Pending",
    }
    return mapping.get(status, status)

"""Governance page — upgrade lifecycle workflow."""
from __future__ import annotations
import pandas as pd
import streamlit as st
from src.api.client import GatewayClient, APIError
from src.auth.session import get_token, get_user
from src.utils.formatters import format_datetime

_STATUS_ICON = {
    "Pending":     "⏳ Pending",
    "Acknowledged":"👁️ Acknowledged",
    "Scheduled":   "📅 Scheduled",
    "In Progress": "🔧 In Progress",
    "Completed":   "✅ Completed",
    "Skipped":     "⏭️ Skipped",
}
_STATUS_COLORS = {
    "Pending": "warning", "Acknowledged": "info", "Scheduled": "info",
    "In Progress": "warning", "Completed": "success", "Skipped": "info",
}
_UPDATE_BADGE = {
    "mandatory":   "🚨 Mandatory",
    "recommended": "⚠️ Recommended",
    "none":        "✅ None",
    "optional":    "✅ Optional",
}


def render() -> None:
    st.title("🔄 Upgrade Governance")
    st.caption("Track every library upgrade from detection to completion. Full human-in-the-loop workflow.")

    client  = GatewayClient(token=get_token())
    username = (get_user() or {}).get("username", "user")

    # ── Summary ────────────────────────────────────────────────────────────────
    with st.spinner("Loading lifecycle data…"):
        try:
            all_lc = client.get_lifecycles().get("data") or []
        except APIError as exc:
            st.error(f"Failed to load lifecycle data: {exc.detail}")
            return

        try:
            libraries = client.get_libraries().get("data", {}).get("libraries", [])
        except APIError:
            libraries = []

    # Count mandatory/recommended libraries without a lifecycle entry
    lc_lib_ids = {lc["library_id"] for lc in all_lc}
    pending_init = [
        l for l in libraries
        if (l.get("update_needed") or "").lower() in ("mandatory", "recommended")
        and l["id"] not in lc_lib_ids
    ]

    # Status breakdown
    status_counts: dict[str, int] = {}
    for lc in all_lc:
        s = lc.get("status", "Pending")
        status_counts[s] = status_counts.get(s, 0) + 1

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Total Tracked",   len(all_lc))
    m2.metric("⏳ Pending",      status_counts.get("Pending", 0))
    m3.metric("📅 Scheduled",    status_counts.get("Scheduled", 0) + status_counts.get("Acknowledged", 0))
    m4.metric("🔧 In Progress",  status_counts.get("In Progress", 0))
    m5.metric("✅ Completed",    status_counts.get("Completed", 0))
    m6.metric("📋 Not Started",  len(pending_init))

    st.divider()

    tab_active, tab_complete, tab_init = st.tabs(["🔄 Active Upgrades", "✅ Completed", "➕ Initialise New"])

    # ══════════════════════════════════════════════════════════════════════
    # Tab 1: Active (non-completed) lifecycle entries
    # ══════════════════════════════════════════════════════════════════════
    with tab_active:
        status_filter = st.selectbox("Filter by status", ["All Active", "Pending", "Acknowledged", "Scheduled", "In Progress"])
        active_statuses = {"Pending", "Acknowledged", "Scheduled", "In Progress"}
        filtered = [
            lc for lc in all_lc
            if lc.get("status") in active_statuses
            and (status_filter == "All Active" or lc.get("status") == status_filter)
        ]

        if not filtered:
            st.info("No active lifecycle entries. Use 'Initialise New' tab to create them.")
        else:
            st.caption(f"{len(filtered)} active upgrade(s)")
            for lc in filtered:
                un    = (lc.get("update_needed") or "").lower()
                badge = _UPDATE_BADGE.get(un, un or "—").split()[0]
                icon  = _STATUS_ICON.get(lc.get("status",""), lc.get("status",""))
                pkg   = lc.get("sdk_name") or lc.get("package") or f"ID:{lc['library_id']}"
                cur   = lc.get("current_version","—")
                lat   = lc.get("latest_version","—")

                with st.expander(f"{badge} {icon}  **{pkg}**  `{cur}` → `{lat}`  — {lc.get('platform','—')}"):
                    c1, c2, c3 = st.columns(3)
                    c1.markdown(f"**Status:** {icon}")
                    c1.markdown(f"**Priority:** {lc.get('priority','—')}")
                    c1.markdown(f"**Update Needed:** {_UPDATE_BADGE.get(un, un)}")
                    c2.markdown(f"**Assigned To:** {lc.get('actioned_by') or 'Unassigned'}")
                    c2.markdown(f"**Sprint:** {lc.get('target_sprint') or '—'}")
                    c2.markdown(f"**Target Date:** {lc.get('target_date') or '—'}")
                    c3.markdown(f"**Target Version:** {lc.get('target_version') or '—'}")
                    c3.markdown(f"**Created:** {format_datetime(lc.get('created_at'))}")
                    c3.markdown(f"**Updated:** {format_datetime(lc.get('updated_at'))}")

                    st.divider()
                    action = st.radio(
                        "Update status",
                        ["— No change —", "👁️ Acknowledge", "📅 Schedule", "🔧 Mark In Progress",
                         "✅ Mark Complete", "⏭️ Skip"],
                        horizontal=True, key=f"action_{lc['id']}",
                    )

                    if action != "— No change —":
                        with st.form(f"form_{lc['id']}"):
                            status_map = {
                                "👁️ Acknowledge":     "Acknowledged",
                                "📅 Schedule":         "Scheduled",
                                "🔧 Mark In Progress": "In Progress",
                                "✅ Mark Complete":    "Completed",
                                "⏭️ Skip":            "Skipped",
                            }
                            new_status = status_map[action]
                            sprint      = st.text_input("Sprint", value=lc.get("target_sprint") or "",
                                                        placeholder="e.g. Sprint-47")  if new_status == "Scheduled" else None
                            target_date = st.date_input("Target Date", value=None) if new_status in ("Scheduled", "In Progress") else None
                            target_ver  = st.text_input("Target Version", value=lc.get("target_version") or "",
                                                        placeholder="e.g. 12.13.0") if new_status in ("Scheduled", "In Progress") else None
                            completed_ver = st.text_input("Completed Version *", placeholder="e.g. 12.13.0") if new_status == "Completed" else None
                            pr_url      = st.text_input("PR / Branch URL", placeholder="https://github.com/...") if new_status == "Completed" else None
                            skip_reason = st.text_area("Skip Reason *", height=60) if new_status == "Skipped" else None
                            reason      = st.text_input("Reason / Notes", placeholder="Optional notes")
                            submitted   = st.form_submit_button(f"Confirm: {action}", type="primary")

                        if submitted:
                            try:
                                if new_status == "Completed":
                                    if not completed_ver or not completed_ver.strip():
                                        st.error("Completed version is required.")
                                    else:
                                        client.complete_lifecycle(
                                            lc["id"], completed_ver.strip(), username,
                                            pr_url=pr_url, reason=reason or None
                                        )
                                        st.success(f"✅ **{pkg}** marked as Completed — library updated to `{completed_ver}`.")
                                        st.rerun()
                                else:
                                    payload: dict = {
                                        "status": new_status,
                                        "actioned_by": username,
                                    }
                                    if sprint:       payload["target_sprint"]  = sprint
                                    if target_date:  payload["target_date"]    = str(target_date)
                                    if target_ver:   payload["target_version"] = target_ver.strip()
                                    if skip_reason:  payload["skip_reason"]    = skip_reason.strip()
                                    client.update_lifecycle(lc["id"], payload)
                                    st.success(f"Updated to **{new_status}**.")
                                    st.rerun()
                            except APIError as exc:
                                st.error(f"Failed: {exc.detail}")

    # ══════════════════════════════════════════════════════════════════════
    # Tab 2: Completed history
    # ══════════════════════════════════════════════════════════════════════
    with tab_complete:
        completed = [lc for lc in all_lc if lc.get("status") in ("Completed", "Skipped")]
        if not completed:
            st.info("No completed upgrades yet.")
        else:
            st.caption(f"{len(completed)} completed upgrade(s)")
            rows = [{
                "SDK":     lc.get("sdk_name") or lc.get("package") or f"ID:{lc['library_id']}",
                "Platform":    lc.get("platform","—"),
                "Status":      _STATUS_ICON.get(lc.get("status",""), lc.get("status","")),
                "Was":         lc.get("current_version","—"),
                "Completed Ver":lc.get("completed_version") or "—",
                "Done By":     lc.get("actioned_by") or "—",
                "Sprint":      lc.get("target_sprint") or "—",
                "Completed At":format_datetime(lc.get("updated_at")),
            } for lc in completed]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════════
    # Tab 3: Initialise lifecycle for untracked libraries
    # ══════════════════════════════════════════════════════════════════════
    with tab_init:
        st.markdown("#### SDKs needing upgrade — not yet in governance workflow")
        if not pending_init:
            st.success("✅ All mandatory/recommended libraries are already tracked in the workflow.")
        else:
            st.caption(f"{len(pending_init)} libraries need upgrade tracking")
            for lib in pending_init:
                un   = (lib.get("update_needed") or "").lower()
                badge = _UPDATE_BADGE.get(un, un)
                with st.expander(f"{badge}  **{lib.get('sdk_name') or lib.get('package','—')}**  `{lib.get('current_version','—')}` → `{lib.get('latest_version','—')}`"):
                    st.markdown(f"Platform: **{lib.get('platform','—')}** | Priority: **{lib.get('priority','—')}**")
                    if st.button("➕ Add to Governance Workflow", key=f"init_{lib['id']}", type="primary"):
                        try:
                            client.init_lifecycle(lib["id"], actioned_by=username)
                            st.success(f"✅ **{lib.get('package')}** added to governance workflow.")
                            st.rerun()
                        except APIError as exc:
                            st.error(f"Failed: {exc.detail}")

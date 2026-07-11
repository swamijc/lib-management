"""SDKs page — enterprise table, version history, CSV export."""
from __future__ import annotations
import io
import pandas as pd
import streamlit as st
from src.api.client import GatewayClient, APIError
from src.auth.session import get_token
from src.utils.formatters import format_registry, format_datetime

_DECISION_BADGE = {"Yes": "🔴 Upgrade", "No": "✅ OK", "Sufficient": "✅ OK"}
_UPDATE_BADGE   = {
    "mandatory":   "🚨 Mandatory",
    "recommended": "⚠️ Recommended",
    "none":        "✅ None",
    "optional":    "✅ Optional",
}
_STATUS_BADGE = {
    "Active":     "🟢 Active",
    "Deprecated": "🔴 Deprecated",
    "Legacy":     "🟡 Legacy",
    "Maintenance":"🔵 Maintenance",
    "Unknown":    "❓ Unknown",
}


def render() -> None:
    st.title("📚 SDKs")

    client = GatewayClient(token=get_token())

    with st.spinner("Loading SDKs…"):
        try:
            libraries = client.get_libraries().get("data", {}).get("libraries", [])
        except APIError as exc:
            st.error(f"Failed to load SDKs: {exc.detail}")
            return

        try:
            recs_raw = client.get_recommendations().get("data") or []
            recs_by_id = {r["library_id"]: r for r in recs_raw}
        except APIError:
            recs_by_id = {}

    if not libraries:
        st.info("No SDKs tracked yet.")
        return

    # ── Summary strip ──────────────────────────────────────────────────────────
    total       = len(libraries)
    mandatory   = sum(1 for l in libraries if (l.get("update_needed") or "").lower() == "mandatory")
    recommended = sum(1 for l in libraries if (l.get("update_needed") or "").lower() == "recommended")
    up_to_date  = sum(1 for l in libraries if (l.get("update_needed") or "").lower() in ("none","optional"))
    deprecated  = sum(1 for l in libraries if (l.get("status") or "").lower() == "deprecated")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total",          total)
    m2.metric("🚨 Mandatory",   mandatory)
    m3.metric("⚠️ Recommended", recommended)
    m4.metric("✅ Up to Date",  up_to_date)
    m5.metric("🔴 Deprecated",  deprecated)
    st.divider()

    # ── Filters ────────────────────────────────────────────────────────────────
    fc1, fc2, fc3, fc4 = st.columns([3, 2, 2, 2])
    search      = fc1.text_input("🔍 Search", "", placeholder="Package or SDK name…")
    platforms   = ["All"] + sorted({l.get("platform","") for l in libraries if l.get("platform")})
    plat_filter = fc2.selectbox("Platform", platforms)
    update_opts = ["All", "🚨 Mandatory", "⚠️ Recommended", "✅ None / Optional", "🔴 Deprecated"]
    upd_filter  = fc3.selectbox("Update Status", update_opts)
    status_opts = ["All"] + sorted({l.get("status","") for l in libraries if l.get("status")})
    sta_filter  = fc4.selectbox("Lib Status", status_opts)

    def _matches(lib: dict) -> bool:
        pkg = (lib.get("package","") + " " + (lib.get("sdk_name") or "")).lower()
        if search and search.lower() not in pkg:            return False
        if plat_filter != "All" and lib.get("platform") != plat_filter: return False
        un = (lib.get("update_needed") or "").lower()
        st_ = (lib.get("status") or "").lower()
        if upd_filter == "🚨 Mandatory"      and un != "mandatory":              return False
        if upd_filter == "⚠️ Recommended"    and un != "recommended":           return False
        if upd_filter == "✅ None / Optional" and un not in ("none","optional"): return False
        if upd_filter == "🔴 Deprecated"      and st_ != "deprecated":          return False
        if sta_filter  != "All" and lib.get("status") != sta_filter:            return False
        return True

    filtered = [l for l in libraries if _matches(l)]
    st.caption(f"Showing **{len(filtered)}** of **{total}** SDKs")

    # ── Data table ─────────────────────────────────────────────────────────────
    rows = []
    for lib in filtered:
        lid = lib.get("id")
        rec = recs_by_id.get(lid, {})
        un  = (lib.get("update_needed") or "").lower()
        rows.append({
            "ID":            lid,
            "SDK Name":      lib.get("sdk_name") or lib.get("package","—"),
            "Package":       lib.get("package","—"),
            "Platform":      lib.get("platform","—"),
            "Language":      lib.get("framework_language","—"),
            "Registry":      format_registry(lib.get("registry")),
            "Current":       lib.get("current_version","—"),
            "Latest":        lib.get("latest_version","—"),
            "Update Needed": _UPDATE_BADGE.get(un, un or "—"),
            "Priority":      lib.get("priority","—"),
            "Status":        _STATUS_BADGE.get(lib.get("status",""), lib.get("status","—")),
            "Recommendation":_DECISION_BADGE.get(rec.get("upgrade_recommended",""), "🟡 Pending"),
            "Deadline":      lib.get("deadline_date") or "—",
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True,
        column_config={
            "ID":            st.column_config.NumberColumn("ID",      width="small"),
            "SDK Name":      st.column_config.TextColumn("SDK Name",  width="medium"),
            "Package":       st.column_config.TextColumn("Package",   width="medium"),
            "Platform":      st.column_config.TextColumn("Platform",  width="small"),
            "Language":      st.column_config.TextColumn("Language",  width="small"),
            "Registry":      st.column_config.TextColumn("Registry",  width="small"),
            "Current":       st.column_config.TextColumn("Current",   width="small"),
            "Latest":        st.column_config.TextColumn("Latest",    width="small"),
            "Update Needed": st.column_config.TextColumn("Update",    width="medium"),
            "Priority":      st.column_config.TextColumn("Priority",  width="small"),
            "Status":        st.column_config.TextColumn("Status",    width="small"),
            "Recommendation":st.column_config.TextColumn("AI Rec.",   width="medium"),
            "Deadline":      st.column_config.TextColumn("Deadline",  width="small"),
        })

    # CSV export
    csv_buf = io.StringIO()
    df.to_csv(csv_buf, index=False)
    st.download_button("⬇️ Export to CSV", csv_buf.getvalue(),
                       file_name="libraries_export.csv", mime="text/csv")

    st.divider()

    # ── Detailed library cards ─────────────────────────────────────────────────
    st.subheader("SDK Details & Version History")
    for lib in filtered:
        lid   = lib.get("id")
        rec   = recs_by_id.get(lid, {})
        un    = (lib.get("update_needed") or "").lower()
        badge = _UPDATE_BADGE.get(un, un or "—")
        icon  = badge.split()[0] if badge else "🟡"
        label = (
            f"{icon}  **{lib.get('sdk_name') or lib.get('package','—')}**  "
            f"`{lib.get('current_version','—')}` → `{lib.get('latest_version','—')}`"
            f"  — {lib.get('platform','—')}"
        )

        with st.expander(label):
            tab_info, tab_rec, tab_hist = st.tabs(["ℹ️ Info", "💡 Recommendation", "📅 Version History"])

            with tab_info:
                c1, c2, c3 = st.columns(3)
                c1.markdown(f"**SDK Name:** {lib.get('sdk_name') or lib.get('package','—')}")
                c1.markdown(f"**Package:** `{lib.get('package','—')}`")
                c1.markdown(f"**Platform:** {lib.get('platform','—')}")
                c1.markdown(f"**Language:** {lib.get('framework_language','—')}")
                c1.markdown(f"**Ecosystem:** {lib.get('ecosystem','—')}")
                c2.markdown(f"**Current:** `{lib.get('current_version','—')}`")
                c2.markdown(f"**Latest:** `{lib.get('latest_version','—')}`")
                c2.markdown(f"**Registry:** {format_registry(lib.get('registry'))}")
                c2.markdown(f"**Repo:** {lib.get('repo_url') or '—'}")
                c3.markdown(f"**Update Needed:** {badge}")
                c3.markdown(f"**Priority:** {lib.get('priority','—')}")
                c3.markdown(f"**Alert Priority:** {lib.get('alert_priority','—')}")
                c3.markdown(f"**Status:** {_STATUS_BADGE.get(lib.get('status',''), lib.get('status','—'))}")
                c3.markdown(f"**Deadline:** {lib.get('deadline_date') or '—'}")
                if lib.get("deadline_notes"):
                    st.info(f"📋 Deadline note: {lib['deadline_notes']}")
                if lib.get("deprecation_notes"):
                    st.warning(f"⚠️ Deprecation: {lib['deprecation_notes']}")
                if lib.get("comments"):
                    st.caption(f"💬 {lib['comments']}")
                st.caption(f"Last updated: {format_datetime(lib.get('updated_at'))}  |  ID: {lid}")

            with tab_rec:
                if rec:
                    decision = rec.get("upgrade_recommended","")
                    summary  = rec.get("recommendation_summary","")
                    if decision == "Yes":
                        st.error(f"🔴 **Recommendation: Upgrade**\n\n{summary}")
                    elif decision in ("No","Sufficient"):
                        st.success(f"✅ **Recommendation: OK**\n\n{summary}")
                    else:
                        st.info(f"🟡 {summary}")

                    pros = rec.get("upgrade_pros") or []
                    cons = rec.get("upgrade_cons") or []
                    if pros or cons:
                        pc1, pc2 = st.columns(2)
                        if pros:
                            pc1.markdown("**Upgrade Pros:**")
                            for p in pros: pc1.markdown(f"  ✅ {p}")
                        if cons:
                            pc2.markdown("**Upgrade Cons:**")
                            for c in cons: pc2.markdown(f"  ⚠️ {c}")
                else:
                    st.info("No AI recommendation yet. Trigger a pipeline run to generate.")

            with tab_hist:
                with st.spinner("Loading version history…"):
                    try:
                        hist_resp = client.get_version_history(lid)
                        hist = hist_resp.get("data") or []
                    except APIError:
                        hist = []
                if hist:
                    df_hist = pd.DataFrame([{
                        "Version":     h.get("version_number","—"),
                        "Type":        h.get("record_type","—"),
                        "Source":      h.get("source","—"),
                        "Recorded At": format_datetime(h.get("recorded_at")),
                        "Notes":       h.get("notes",""),
                    } for h in hist])
                    st.dataframe(df_hist, use_container_width=True, hide_index=True)
                else:
                    st.caption("No version history records for this library.")

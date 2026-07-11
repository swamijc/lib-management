"""Dashboard — enterprise-level summary with charts and live data."""
from __future__ import annotations
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from src.api.client import GatewayClient, APIError
from src.auth.session import get_token
from src.utils.formatters import format_datetime, format_pipeline_status

_STATUS_COLORS = {
    "mandatory":   "#EF4444",
    "recommended": "#F59E0B",
    "none":        "#10B981",
    "optional":    "#10B981",
}
_PLATFORM_COLORS = {"Android": "#3DDC84", "iOS": "#007AFF", "Both": "#8B5CF6"}


def _pie(labels, values, colors, title):
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        marker_colors=colors,
        hole=0.55,
        textinfo="label+percent",
        hovertemplate="%{label}: %{value} (%{percent})<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text=title, font_size=13, x=0.5),
        showlegend=False,
        margin=dict(t=40, b=10, l=10, r=10),
        height=220,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def _bar(labels, values, colors, title):
    fig = go.Figure(go.Bar(
        x=labels, y=values,
        marker_color=colors,
        text=values, textposition="outside",
        hovertemplate="%{x}: %{y}<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text=title, font_size=13, x=0.5),
        yaxis=dict(showticklabels=False, showgrid=False, zeroline=False),
        xaxis=dict(showgrid=False),
        margin=dict(t=40, b=10, l=10, r=10),
        height=220,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def render() -> None:
    st.title("🏠 Dashboard")

    client = GatewayClient(token=get_token())

    # ── Fetch data ─────────────────────────────────────────────────────────────
    with st.spinner("Loading dashboard data…"):
        try:
            libraries = client.get_libraries().get("data", {}).get("libraries", [])
        except APIError:
            libraries = []
            st.error("⚠️ Could not load library data from service.")

        try:
            recs_raw = client.get_recommendations().get("data") or []
            recs_by_id = {r["library_id"]: r for r in recs_raw if isinstance(recs_raw, list)}
        except APIError:
            recs_by_id = {}

        try:
            runs = client.get_runs().get("data") or []
            runs = runs if isinstance(runs, list) else []
        except APIError:
            runs = []

        # NEW: SLA summary (non-blocking)
        try:
            sla = client.get_sla_summary().get("data") or {}
        except APIError:
            sla = {}

        # NEW: Lifecycle summary
        try:
            all_lc = client.get_lifecycles().get("data") or []
            lc_counts: dict[str, int] = {}
            for lc in all_lc:
                s = lc.get("status","Pending")
                lc_counts[s] = lc_counts.get(s, 0) + 1
        except APIError:
            lc_counts = {}

        # NEW: CVE summary
        try:
            cve_cached = client.get_cve_cache().get("data") or []
            cve_libs_with_vulns = sum(1 for c in cve_cached if c.get("vuln_count",0) > 0)
            cve_total_vulns = sum(c.get("vuln_count",0) for c in cve_cached)
        except APIError:
            cve_libs_with_vulns = 0
            cve_total_vulns = 0

    if not libraries:
        st.warning("No library data available. Check service connectivity.")
        return

    # ── Aggregate metrics ──────────────────────────────────────────────────────
    total      = len(libraries)
    mandatory  = sum(1 for l in libraries if (l.get("update_needed") or "").lower() == "mandatory")
    recommended= sum(1 for l in libraries if (l.get("update_needed") or "").lower() == "recommended")
    up_to_date = sum(1 for l in libraries if (l.get("update_needed") or "").lower() in ("none", "optional"))
    deprecated = sum(1 for l in libraries if (l.get("status") or "").lower() == "deprecated")
    android    = sum(1 for l in libraries if l.get("platform") == "Android")
    ios        = sum(1 for l in libraries if l.get("platform") == "iOS")

    # Use recommendations if available (populated by pipeline run)
    # Fall back to library update_needed field if no recs yet
    if recs_by_id:
        rec_upgrade = sum(1 for r in recs_by_id.values() if r.get("upgrade_recommended") == "Yes")
        rec_ok      = sum(1 for r in recs_by_id.values() if r.get("upgrade_recommended") in ("No", "Sufficient"))
    else:
        # No pipeline run yet — fall back to library update_needed field
        rec_upgrade = mandatory + recommended
        rec_ok      = up_to_date

    # ── Risk Score calculation ─────────────────────────────────────────────────
    # Formula: mandatory×3 + deprecated×2 + overdue×5 — normalised 0–100
    raw_score = (mandatory * 3) + (deprecated * 2) + (rec_upgrade * 1)
    max_possible = total * 3 if total > 0 else 1
    risk_score = min(100, int((raw_score / max_possible) * 100)) if total > 0 else 0
    risk_level = ("🔴 Critical" if risk_score >= 70 else
                  "🟠 High"     if risk_score >= 50 else
                  "🟡 Medium"   if risk_score >= 30 else
                  "🟢 Low")

    # ── Top KPI strip ──────────────────────────────────────────────────────────
    st.markdown("### 📊 Portfolio Overview")
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Total SDKs",  total)
    k2.metric("🚨 Mandatory",     mandatory,   delta=f"{mandatory/total*100:.0f}%" if total else "0%", delta_color="inverse")
    k3.metric("⚠️ Recommended",   recommended, delta=f"{recommended/total*100:.0f}%" if total else "0%", delta_color="inverse")
    k4.metric("✅ Up to Date",     up_to_date,  delta=f"{up_to_date/total*100:.0f}%" if total else "0%")
    k5.metric("🔴 Deprecated",    deprecated,  delta_color="inverse")
    k6.metric(f"Risk Score: {risk_level}", risk_score,
              delta=f"{risk_level}", delta_color="inverse" if risk_score >= 50 else "normal")

    st.divider()

    # ── Charts row ─────────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)

    with c1:
        update_labels = ["Mandatory", "Recommended", "Up to Date", "Deprecated"]
        update_values = [mandatory, recommended, up_to_date, deprecated]
        update_colors = ["#EF4444", "#F59E0B", "#10B981", "#6B7280"]
        st.plotly_chart(
            _pie(update_labels, update_values, update_colors, "Upgrade Status"),
            use_container_width=True, key="pie_update",
        )

    with c2:
        plat_labels = ["Android", "iOS", "Both"]
        plat_values = [android, ios, total - android - ios]
        plat_colors = ["#3DDC84", "#007AFF", "#8B5CF6"]
        st.plotly_chart(
            _pie(plat_labels, plat_values, plat_colors, "Platform Breakdown"),
            use_container_width=True, key="pie_platform",
        )

    with c3:
        # Status breakdown
        status_counts: dict[str, int] = {}
        for lib in libraries:
            s = lib.get("status", "Unknown")
            status_counts[s] = status_counts.get(s, 0) + 1
        sc_labels = list(status_counts.keys())
        sc_values = list(status_counts.values())
        sc_colors = {"Active": "#10B981", "Deprecated": "#EF4444", "Legacy": "#F59E0B",
                     "Maintenance": "#3B82F6", "Unknown": "#9CA3AF"}
        st.plotly_chart(
            _bar(sc_labels, sc_values, [sc_colors.get(l, "#9CA3AF") for l in sc_labels], "SDK Status"),
            use_container_width=True, key="bar_status",
        )

    st.divider()

    # ── SLA + Lifecycle + CVE row ──────────────────────────────────────────────
    sw1, sw2, sw3 = st.columns(3)

    with sw1:
        st.markdown("#### ⏰ SLA Status")
        sla_pct = sla.get("sla_compliance_pct", None)
        overdue = sla.get("overdue", 0)
        due7    = sla.get("due_within_7_days", 0)
        if sla:
            if overdue > 0:
                st.error(f"🚨 **{overdue}** SDKs overdue")
            if due7 > 0:
                st.warning(f"⚠️ **{due7}** due within 7 days")
            if overdue == 0 and due7 == 0:
                st.success("✅ No overdue or imminent deadlines")
            if sla_pct is not None:
                st.metric("SLA Compliance", f"{sla_pct:.1f}%")
            st.caption(f"Deadlines set: {sla.get('with_deadline',0)} SDKs | [View Reports →](?page=reports)")
        else:
            st.info("No SLA data. Set deadline_date on SDKs in Management.")

    with sw2:
        st.markdown("#### 🔄 Lifecycle Status")
        if lc_counts:
            lc_total = sum(lc_counts.values())
            completed = lc_counts.get("Completed", 0)
            waiting   = lc_counts.get("Pending", 0) + lc_counts.get("Acknowledged", 0)
            in_flight = lc_counts.get("In Progress", 0) + lc_counts.get("Scheduled", 0)
            if lc_total > 0:
                pct = completed / lc_total * 100
                st.metric("Overall Progress", f"{pct:.0f}%", delta=f"{completed}/{lc_total} done")
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("⏳ Waiting",     waiting)
            col_b.metric("🔧 Active",      in_flight)
            col_c.metric("✅ Done",        completed)
            st.caption(f"[Go to Governance →](?page=governance)")
        else:
            st.info("No lifecycle entries. Go to Governance to track upgrades.")
            st.caption("Add SDKs to the governance workflow to track who is upgrading what.")

    with sw3:
        st.markdown("#### 🔐 CVE Security")
        if cve_cached:
            if cve_libs_with_vulns > 0:
                st.error(f"🚨 **{cve_libs_with_vulns}** SDKs have known CVEs ({cve_total_vulns} total)")
            else:
                st.success(f"✅ {len(cve_cached)} SDKs scanned — no vulnerabilities")
            scanned_pct = len(cve_cached) / total * 100 if total > 0 else 0
            st.metric("SDKs Scanned", f"{len(cve_cached)}/{total}", delta=f"{scanned_pct:.0f}% coverage")
            st.caption("Scan SDKs via Package Profile → CVE tab")
        else:
            st.info("No CVE scans yet.")
            st.caption("Open any SDK in 📦 Package Profile and click 'Scan for CVEs' to start.")

    st.divider()

    # ── Priority breakdown table ────────────────────────────────────────────────
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("#### 🔴 Mandatory Upgrades")
        mandatory_libs = [l for l in libraries if (l.get("update_needed") or "").lower() == "mandatory"]
        if mandatory_libs:
            df_mand = pd.DataFrame([{
                "Package":   l.get("sdk_name") or l.get("package", "—"),
                "Platform":  l.get("platform", "—"),
                "Current":   l.get("current_version", "—"),
                "Latest":    l.get("latest_version", "—"),
                "Status":    l.get("status", "—"),
                "Deadline":  l.get("deadline_date") or "—",
            } for l in mandatory_libs[:10]])
            st.dataframe(df_mand, use_container_width=True, hide_index=True)
            if len(mandatory_libs) > 10:
                st.caption(f"Showing 10 of {len(mandatory_libs)}. See SDKs page for full list.")
        else:
            st.success("✅ No mandatory upgrades pending.")

    with col_right:
        st.markdown("#### 🔔 Critical & High Alert SDKs")
        alert_libs = [l for l in libraries if (l.get("alert_priority") or "Normal") in ("Critical", "High")]
        if alert_libs:
            df_alert = pd.DataFrame([{
                "Package":  l.get("sdk_name") or l.get("package", "—"),
                "Platform": l.get("platform", "—"),
                "Priority": l.get("alert_priority", "—"),
                "Status":   l.get("status", "—"),
                "Update":   l.get("update_needed", "—"),
            } for l in alert_libs[:10]])
            st.dataframe(df_alert, use_container_width=True, hide_index=True)
        else:
            st.info("No high/critical alert libraries.")

    st.divider()

    # ── Recent pipeline runs ────────────────────────────────────────────────────
    st.markdown("#### 🔄 Recent Pipeline Runs")
    if not runs:
        st.info("No pipeline runs yet.")
        if st.button("▶️ Trigger First Run →", type="primary"):
            st.switch_page("scheduler")
    else:
        df_runs = pd.DataFrame([{
            "Run ID":    str(r.get("run_id", "—"))[:12] + "…",
            "Status":    format_pipeline_status(r.get("status", "unknown")),
            "Triggered": r.get("triggered_by", "—"),
            "SDKs": r.get("libraries_processed", 0),
            "Updated":   r.get("libraries_updated", 0),
            "Errors":    r.get("errors_count", 0),
            "Started":   format_datetime(r.get("started_at")),
            "Duration":  f"{r.get('duration_seconds', '—')}s" if r.get("duration_seconds") else "—",
        } for r in runs[:10]])
        st.dataframe(df_runs, use_container_width=True, hide_index=True)

    # ── Last data refresh ───────────────────────────────────────────────────────
    import datetime
    last_updated = max((l.get("updated_at") or "") for l in libraries) if libraries else ""
    st.caption(
        f"Data refreshed: {format_datetime(last_updated) if last_updated else 'unknown'}  |  "
        f"{total} libraries tracked  |  "
        f"{len(recs_by_id)} recommendations available"
    )

"""Reports page — Executive PDF report + SLA dashboard + portfolio export."""
from __future__ import annotations
import io
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from src.api.client import GatewayClient, APIError
from src.auth.session import get_token
from src.utils.formatters import format_datetime

_UPDATE_BADGE = {"mandatory":"🚨 Mandatory","recommended":"⚠️ Recommended","none":"✅ None","optional":"✅ Optional"}


def _generate_pdf(libs: list[dict], sla_summary: dict, lc_counts: dict, llm_stats: dict) -> bytes:
    """Generate an executive PDF report using fpdf2."""
    from fpdf import FPDF

    class PDF(FPDF):
        def header(self):
            self.set_font("Helvetica", "B", 14)
            self.set_fill_color(30, 64, 175)
            self.set_text_color(255, 255, 255)
            self.cell(0, 10, "SDK Management — Executive Report", border=0, fill=True, align="C")
            self.ln(2)
            self.set_font("Helvetica", "", 9)
            self.set_text_color(100, 100, 100)
            self.cell(0, 6, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}", align="C")
            self.ln(6)
            self.set_text_color(0, 0, 0)

        def footer(self):
            self.set_y(-12)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(150, 150, 150)
            self.cell(0, 8, f"Page {self.page_no()} | Confidential", align="C")

        def section_title(self, title: str):
            self.set_font("Helvetica", "B", 11)
            self.set_fill_color(239, 246, 255)
            self.set_text_color(30, 64, 175)
            self.cell(0, 8, f"  {title}", border="B", fill=True)
            self.ln(4)
            self.set_text_color(0, 0, 0)

        def kpi_row(self, items: list[tuple[str, str]]):
            """Render a row of KPI boxes."""
            w = (self.epw) / len(items)
            for label, value in items:
                self.set_font("Helvetica", "", 8)
                self.set_fill_color(248, 250, 252)
                self.cell(w - 2, 5, label, border=0, fill=True, align="C")
                self.set_x(self.get_x() - (w - 2) + 2)
            self.ln(5)
            for label, value in items:
                self.set_font("Helvetica", "B", 14)
                self.set_fill_color(248, 250, 252)
                self.cell(w - 2, 8, value, border=0, fill=True, align="C")
                self.set_x(self.get_x() - (w - 2) + 2)
            self.ln(10)

    pdf = PDF(orientation="P", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    total      = len(libs)
    mandatory  = sum(1 for l in libs if (l.get("update_needed") or "").lower() == "mandatory")
    recommended= sum(1 for l in libs if (l.get("update_needed") or "").lower() == "recommended")
    up_to_date = sum(1 for l in libs if (l.get("update_needed") or "").lower() in ("none","optional"))
    deprecated = sum(1 for l in libs if (l.get("status") or "").lower() == "deprecated")
    android    = sum(1 for l in libs if l.get("platform") == "Android")
    ios        = sum(1 for l in libs if l.get("platform") == "iOS")

    # ── Portfolio overview ────────────────────────────────────────────────────
    pdf.section_title("1. Portfolio Overview")
    pdf.kpi_row([
        ("Total SDKs", str(total)),
        ("Android", str(android)),
        ("iOS", str(ios)),
        ("Mandatory Upgrades", str(mandatory)),
        ("Recommended", str(recommended)),
        ("Up to Date", str(up_to_date)),
    ])

    # ── SLA Summary ───────────────────────────────────────────────────────────
    pdf.section_title("2. SLA & Compliance")
    overdue     = sla_summary.get("overdue", 0)
    sla_pct     = sla_summary.get("sla_compliance_pct", 100)
    pdf.kpi_row([
        ("SLA Compliance", f"{sla_pct}%"),
        ("Overdue",        str(overdue)),
        ("Due in 7 Days",  str(sla_summary.get("due_within_7_days",0))),
        ("Due in 30 Days", str(sla_summary.get("due_within_30_days",0))),
    ])

    # ── Lifecycle Summary ─────────────────────────────────────────────────────
    pdf.section_title("3. Upgrade Governance Status")
    pdf.kpi_row([
        ("Pending",     str(lc_counts.get("Pending",0))),
        ("Acknowledged",str(lc_counts.get("Acknowledged",0))),
        ("Scheduled",   str(lc_counts.get("Scheduled",0))),
        ("In Progress", str(lc_counts.get("In Progress",0))),
        ("Completed",   str(lc_counts.get("Completed",0))),
        ("Skipped",     str(lc_counts.get("Skipped",0))),
    ])

    # ── LLM Analytics ────────────────────────────────────────────────────────
    if llm_stats.get("total_calls", 0) > 0:
        pdf.section_title("4. AI Cost Metrics")
        cost  = llm_stats.get("total_cost_usd", 0)
        hrs   = llm_stats.get("total_calls", 0) * 0.75
        saved = hrs * 80
        pdf.kpi_row([
            ("Total AI Calls",    str(llm_stats.get("total_calls",0))),
            ("Total Tokens",      f"{llm_stats.get('total_tokens',0):,}"),
            ("Total AI Cost",     f"${cost:.4f}"),
            ("Hours Saved (est)", f"{hrs:.0f} hrs"),
            ("Value Saved (est)", f"${saved:.0f}"),
            ("ROI",               f"{saved/max(cost,0.001):.0f}x"),
        ])

    # ── Mandatory upgrades table ──────────────────────────────────────────────
    mandatory_libs = [l for l in libs if (l.get("update_needed") or "").lower() == "mandatory"]
    if mandatory_libs:
        pdf.section_title(f"5. Mandatory Upgrades ({len(mandatory_libs)} libraries)")
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(30, 64, 175)
        pdf.set_text_color(255, 255, 255)
        cols = [("SDK Name",50),("Platform",22),("Current",25),("Latest",25),("Deadline",25),("Priority",22)]
        for label, w in cols:
            pdf.cell(w, 6, label, border=0, fill=True, align="C")
        pdf.ln()
        pdf.set_text_color(0, 0, 0)
        for i, lib in enumerate(mandatory_libs[:20]):
            pdf.set_fill_color(248,250,252) if i%2==0 else pdf.set_fill_color(255,255,255)
            pdf.set_font("Helvetica", "", 7)
            name = (lib.get("sdk_name") or lib.get("package","—"))[:28]
            data_row = [
                (name, 50), (lib.get("platform","—"), 22),
                (lib.get("current_version","—") or "—", 25),
                (lib.get("latest_version","—") or "—", 25),
                (lib.get("deadline_date") or "—", 25),
                (lib.get("priority","—") or "—", 22),
            ]
            for val, w in data_row:
                pdf.cell(w, 5, str(val), fill=True)
            pdf.ln()
        if len(mandatory_libs) > 20:
            pdf.set_font("Helvetica", "I", 7)
            pdf.cell(0, 5, f"  ... and {len(mandatory_libs)-20} more. Export full CSV for complete list.")
            pdf.ln()

    return bytes(pdf.output())


def render() -> None:
    st.title("📑 Reports")
    st.caption("Executive PDF report, SLA dashboard, and portfolio analytics.")

    client = GatewayClient(token=get_token())

    with st.spinner("Loading report data…"):
        try:
            libs     = client.get_libraries().get("data",{}).get("libraries",[])
        except APIError:
            libs = []
        try:
            sla_sum  = client.get_sla_summary().get("data",{})
        except APIError:
            sla_sum  = {}
        try:
            all_lc   = client.get_lifecycles().get("data") or []
            lc_counts: dict[str,int] = {}
            for lc in all_lc:
                s = lc.get("status","Pending")
                lc_counts[s] = lc_counts.get(s,0) + 1
        except APIError:
            lc_counts = {}
        try:
            llm_stats = client.get_llm_usage().get("data",{}).get("stats",{})
        except APIError:
            llm_stats = {}
        try:
            overdue_libs = client.get_sla_overdue().get("data") or []
        except APIError:
            overdue_libs = []
        try:
            approaching = client.get_sla_approaching(days_ahead=30).get("data") or []
        except APIError:
            approaching = []

    tab_sla, tab_lifecycle, tab_pdf, tab_export = st.tabs([
        "⏰ SLA Dashboard", "🔄 Lifecycle Overview", "📄 PDF Report", "⬇️ Data Export"
    ])

    # ══════════════════════════════════════════════════════════════════════
    with tab_sla:
        st.markdown("### SLA Compliance Dashboard")
        s1, s2, s3, s4, s5 = st.columns(5)
        s1.metric("SLA Compliance",    f"{sla_sum.get('sla_compliance_pct',100):.1f}%",
                  delta="target: 90%", delta_color="normal" if sla_sum.get("sla_compliance_pct",100)>=90 else "inverse")
        s2.metric("🚨 Overdue",        sla_sum.get("overdue",0),     delta_color="inverse")
        s3.metric("⚠️ Due in 7 days",  sla_sum.get("due_within_7_days",0),  delta_color="inverse")
        s4.metric("📅 Due in 30 days", sla_sum.get("due_within_30_days",0), delta_color="inverse")
        s5.metric("✅ With Deadline",   sla_sum.get("with_deadline",0))
        st.divider()

        if overdue_libs:
            st.error(f"🚨 **{len(overdue_libs)} libraries are OVERDUE** — past their deadline without upgrade")
            df_ov = pd.DataFrame([{
                "SDK":     l.get("sdk_name") or l.get("package","—"),
                "Platform":    l.get("platform","—"),
                "Current":     l.get("current_version","—"),
                "Latest":      l.get("latest_version","—"),
                "Update":      _UPDATE_BADGE.get((l.get("update_needed") or "").lower(), "—"),
                "Deadline":    l.get("deadline_date","—"),
                "Days Overdue":l.get("days_overdue",0),
                "Priority":    l.get("priority","—"),
            } for l in overdue_libs])
            st.dataframe(df_ov, use_container_width=True, hide_index=True)
        else:
            st.success("✅ No overdue libraries.")

        if approaching:
            st.warning(f"⚠️ **{len(approaching)} libraries** have deadlines in the next 30 days")
            df_ap = pd.DataFrame([{
                "SDK":    l.get("sdk_name") or l.get("package","—"),
                "Platform":   l.get("platform","—"),
                "Current":    l.get("current_version","—"),
                "Latest":     l.get("latest_version","—"),
                "Deadline":   l.get("deadline_date","—"),
                "Days Left":  l.get("days_until",0),
            } for l in approaching])
            st.dataframe(df_ap, use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════════
    with tab_lifecycle:
        st.markdown("### Upgrade Governance Overview")
        if not lc_counts:
            st.info("No lifecycle tracking entries yet. Go to **🔄 Governance** page to add libraries to the workflow.")
        else:
            # Status distribution chart
            statuses = ["Pending","Acknowledged","Scheduled","In Progress","Completed","Skipped"]
            colors   = ["#9CA3AF","#3B82F6","#8B5CF6","#F59E0B","#10B981","#6B7280"]
            vals     = [lc_counts.get(s,0) for s in statuses]
            fig = go.Figure(go.Bar(
                x=statuses, y=vals, marker_color=colors,
                text=vals, textposition="outside",
                hovertemplate="%{x}: %{y}<extra></extra>",
            ))
            fig.update_layout(
                height=250, margin=dict(t=10,b=10,l=10,r=10),
                yaxis=dict(showgrid=False, showticklabels=False),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True, key="lc_bar")

            # Progress towards completion
            total_tracked = sum(vals)
            completed     = lc_counts.get("Completed",0)
            in_flight     = lc_counts.get("In Progress",0) + lc_counts.get("Scheduled",0)
            waiting       = lc_counts.get("Pending",0) + lc_counts.get("Acknowledged",0)
            if total_tracked > 0:
                pct = completed / total_tracked * 100
                st.markdown(f"**Overall Progress:** {completed}/{total_tracked} completed ({pct:.1f}%)")
                st.progress(pct/100)
                st.caption(f"In flight: {in_flight}  |  Waiting for action: {waiting}  |  Completed: {completed}")

    # ══════════════════════════════════════════════════════════════════════
    with tab_pdf:
        st.markdown("### Executive PDF Report")
        st.caption(
            "One-click PDF suitable for management presentations. "
            "Includes: portfolio overview, SLA compliance, governance status, "
            "mandatory upgrades table, and AI cost metrics."
        )
        if st.button("📄 Generate PDF Report", type="primary"):
            with st.spinner("Generating PDF…"):
                try:
                    pdf_bytes = _generate_pdf(libs, sla_sum, lc_counts, llm_stats)
                    fname = f"library_report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
                    st.download_button(
                        label="⬇️ Download PDF Report",
                        data=pdf_bytes,
                        file_name=fname,
                        mime="application/pdf",
                        type="primary",
                    )
                    st.success(f"✅ PDF generated — {len(pdf_bytes):,} bytes. Click above to download.")
                except Exception as exc:
                    st.error(f"PDF generation failed: {exc}")

    # ══════════════════════════════════════════════════════════════════════
    with tab_export:
        st.markdown("### Full Data Export")
        if libs:
            df_all = pd.DataFrame([{
                "ID":            l.get("id"),
                "Package":       l.get("package",""),
                "SDK Name":      l.get("sdk_name") or l.get("package",""),
                "Platform":      l.get("platform",""),
                "Language":      l.get("framework_language",""),
                "Registry":      l.get("registry",""),
                "Current":       l.get("current_version",""),
                "Latest":        l.get("latest_version",""),
                "Update Needed": l.get("update_needed",""),
                "Status":        l.get("status",""),
                "Priority":      l.get("priority",""),
                "Alert Priority":l.get("alert_priority",""),
                "Deadline":      l.get("deadline_date",""),
                "Deadline Notes":l.get("deadline_notes",""),
                "Ecosystem":     l.get("ecosystem",""),
                "Repo URL":      l.get("repo_url",""),
                "Comments":      l.get("comments",""),
                "Deprecation":   l.get("deprecation_notes",""),
                "Last Checked":  l.get("last_checked_date",""),
                "Updated At":    l.get("updated_at",""),
            } for l in libs])
            st.dataframe(df_all, use_container_width=True, hide_index=True)
            buf = io.StringIO()
            df_all.to_csv(buf, index=False)
            st.download_button(
                "⬇️ Export All SDKs (CSV)",
                buf.getvalue(), file_name="libraries_full_export.csv", mime="text/csv"
            )

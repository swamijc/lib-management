"""Audit Trail page — immutable change history for all library updates."""
from __future__ import annotations
import io
import pandas as pd
import streamlit as st
from src.api.client import GatewayClient, APIError
from src.auth.session import get_token
from src.utils.formatters import format_datetime

_FIELD_LABELS = {
    "current_version":   "📦 Current Version",
    "latest_version":    "🆕 Latest Version",
    "update_needed":     "⚠️ Update Status",
    "status":            "🔵 SDK Status",
    "priority":          "⭐ Priority",
    "alert_priority":    "🔔 Alert Priority",
    "comments":          "💬 Comments",
    "deprecation_notes": "⛔ Deprecation Notes",
    "deadline_date":     "📅 Deadline",
    "lifecycle_complete":"✅ Lifecycle Completed",
}


def render() -> None:
    st.title("📋 Audit Trail")
    st.caption("Immutable record of every change made to library data. Cannot be edited or deleted.")

    client = GatewayClient(token=get_token())

    # ── Filters ────────────────────────────────────────────────────────────────
    with st.expander("🔍 Filter Audit Log", expanded=False):
        fc1, fc2, fc3, fc4 = st.columns(4)
        lib_id     = fc1.number_input("SDK ID", min_value=0, value=0, step=1,
                                       help="0 = show all")
        user_filter = fc2.text_input("Changed By", placeholder="username")
        date_from   = fc3.date_input("From Date", value=None)
        date_to     = fc4.date_input("To Date",   value=None)

    with st.spinner("Loading audit log…"):
        try:
            resp = client.get_audit_log(
                library_id=int(lib_id) if lib_id > 0 else None,
                updated_by=user_filter.strip() or None,
                date_from=str(date_from) if date_from else None,
                date_to=str(date_to)   if date_to   else None,
                limit=300,
            )
            entries = resp.get("data") or []
        except APIError as exc:
            st.error(f"Failed to load audit log: {exc.detail}")
            return

    if not entries:
        st.info("No audit log entries yet. Changes to libraries will appear here.")
        st.markdown("""
**Audit events are created when:**
- An admin edits a library's fields (version, status, priority, etc.)
- A developer marks an upgrade as completed via the Governance workflow
- The scheduler pipeline updates library versions from scrape results
""")
        return

    st.caption(f"**{len(entries)}** changes on record")

    # ── Summary metrics ────────────────────────────────────────────────────────
    unique_users   = len({e.get("updated_by","") for e in entries})
    unique_libs    = len({e.get("library_id", 0) for e in entries})
    manual_changes = sum(1 for e in entries if e.get("update_type") == "manual")
    auto_changes   = len(entries) - manual_changes

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Changes",   len(entries))
    m2.metric("SDKs Affected", unique_libs)
    m3.metric("Contributors",    unique_users)
    m4.metric("Manual / Auto",   f"{manual_changes} / {auto_changes}")
    st.divider()

    # ── Audit table ────────────────────────────────────────────────────────────
    rows = [{
        "Timestamp":  format_datetime(e.get("updated_at")),
        "SDK":    e.get("sdk_name") or e.get("package") or f"ID:{e.get('library_id')}",
        "Changed By": e.get("updated_by", "—"),
        "Type":       e.get("update_type", "—"),
        "Field":      _FIELD_LABELS.get(e.get("field_changed",""), e.get("field_changed","—")),
        "From":       e.get("old_value") or "—",
        "To":         e.get("new_value") or "—",
        "Reason":     (e.get("reason") or "—")[:80],
    } for e in entries]

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True,
        column_config={
            "Timestamp":  st.column_config.TextColumn("Timestamp",   width="medium"),
            "SDK":    st.column_config.TextColumn("SDK",     width="medium"),
            "Changed By": st.column_config.TextColumn("Changed By",  width="small"),
            "Type":       st.column_config.TextColumn("Type",        width="small"),
            "Field":      st.column_config.TextColumn("Field",       width="medium"),
            "From":       st.column_config.TextColumn("From",        width="small"),
            "To":         st.column_config.TextColumn("To",          width="small"),
            "Reason":     st.column_config.TextColumn("Reason",      width="large"),
        })

    buf = io.StringIO()
    df.to_csv(buf, index=False)
    st.download_button("⬇️ Export Audit Log (CSV)", buf.getvalue(),
                       file_name="audit_log.csv", mime="text/csv")

"""Notifications page — log + channel configuration status."""
from __future__ import annotations
import pandas as pd
import streamlit as st
from src.api.client import GatewayClient, APIError
from src.auth.session import get_token
from src.utils.formatters import format_datetime


def render() -> None:
    st.title("🔔 Notifications")
    client = GatewayClient(token=get_token())

    tab_log, tab_status = st.tabs(["📋 Notification Log", "🔧 Channel Status"])

    # ══════════════════════════════════════════════════════════════════════
    # Tab 1: Log
    # ══════════════════════════════════════════════════════════════════════
    with tab_log:
        col_r, _ = st.columns([1, 5])
        if col_r.button("🔄 Refresh"):
            st.rerun()

        with st.spinner("Loading notifications…"):
            try:
                entries = client.get_notifications_log().get("data") or []
                entries = entries if isinstance(entries, list) else []
            except APIError as exc:
                st.error(f"Could not load notifications: {exc.detail}")
                entries = []

        if not entries:
            st.info("📭 No notifications sent yet.")
            st.markdown(
                "Notifications are triggered automatically when a pipeline run detects "
                "mandatory or recommended upgrades. Configure channels in the **⚙️ Settings → Notifications** tab."
            )
        else:
            st.caption(f"{len(entries)} notification(s) on record")
            rows = [{
                "Channel":    ("📧 Email" if e.get("channel","")=="email" else "💬 Teams"),
                "Subject":    e.get("subject","—"),
                "Recipients": e.get("recipients","—"),
                "Sent At":    format_datetime(e.get("sent_at")),
                "Preview":    (e.get("body_preview") or "")[:120],
            } for e in entries]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════════
    # Tab 2: Channel status
    # ══════════════════════════════════════════════════════════════════════
    with tab_status:
        st.markdown("### Notification Channel Status")
        st.caption("Configure channels in **⚙️ Settings → 🔧 Notifications Config** tab.")

        with st.spinner("Loading app settings…"):
            try:
                app_cfg = {s["key"]: s["value"] for s in
                           (client.get_app_settings().get("data") or [])}
            except APIError:
                app_cfg = {}

        email_enabled = app_cfg.get("email_enabled","0") == "1"
        teams_enabled = app_cfg.get("teams_enabled","0") == "1"
        recipients    = app_cfg.get("email_recipients","[]")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### 📧 Email")
            if email_enabled:
                st.success("🟢 Email notifications are **enabled**")
                st.caption(f"Recipients: `{recipients}`")
            else:
                st.warning("⚪ Email notifications are **disabled**")
                st.caption("Enable in Settings → Notifications Config.")

        with c2:
            st.markdown("#### 💬 Microsoft Teams")
            if teams_enabled:
                st.success("🟢 Teams notifications are **enabled**")
            else:
                st.warning("⚪ Teams notifications are **disabled**")
                st.caption("Enable in Settings → Notifications Config.")

        st.divider()
        st.markdown("#### 📊 Notification Triggers")
        st.markdown("""
| Trigger | Condition | Channel |
|---------|-----------|---------|
| Mandatory upgrade detected | `update_needed = mandatory` | Email + Teams |
| Recommended upgrade | `update_needed = recommended` | Email |
| Deprecated library | `status = Deprecated` | Teams |
| Pipeline run completed | Always after a run | Email summary |
""")

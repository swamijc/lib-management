"""Teams page — squad/team management and library ownership."""
from __future__ import annotations
import pandas as pd
import streamlit as st
from src.api.client import GatewayClient, APIError
from src.auth.session import get_token, get_user, is_admin
from src.utils.formatters import format_datetime

_UPDATE_BADGE = {"mandatory":"🚨 Mandatory","recommended":"⚠️ Recommended","none":"✅ None","optional":"✅ Optional"}


def render() -> None:
    st.title("👥 Teams & Ownership")
    st.caption("Assign libraries to squads. Each squad sees their upgrade responsibilities in one place.")

    client   = GatewayClient(token=get_token())
    username = (get_user() or {}).get("username", "admin")

    with st.spinner("Loading teams…"):
        try:
            teams = client.get_teams().get("data") or []
        except APIError as exc:
            st.error(f"Failed to load teams: {exc.detail}"); return

    tab_view, tab_create, tab_assign = st.tabs(["📋 Teams Overview", "➕ Create Team", "🔗 Assign SDKs"])

    # ══════════════════════════════════════════════════════════════════════
    with tab_view:
        if not teams:
            st.info("No teams yet. Create your first squad in the '➕ Create Team' tab.")
            st.markdown("""
**Suggested squads for a mobile team:**
- `Android Core` — Android platform libraries
- `iOS Core` — iOS/Swift platform libraries
- `Payments` — payment-related SDKs (Braintree, PayPal, Klarna)
- `Analytics` — analytics/tracking SDKs (Firebase, Adobe, AppsFlyer)
- `Security` — security-critical libraries (SQLCipher, SSL)
""")
        else:
            # Summary metrics
            total_assigned = sum(t.get("library_count",0) for t in teams)
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Teams",       len(teams))
            m2.metric("SDKs Assigned", total_assigned)
            m3.metric("Unassigned",        max(0, 119 - total_assigned))
            st.divider()

            for team in teams:
                tid = team["id"]
                with st.expander(f"**{team['team_name']}**  — {team.get('library_count',0)} libraries", expanded=False):
                    c1, c2 = st.columns(2)
                    c1.markdown(f"**Email:** {team.get('team_email') or '—'}")
                    c2.markdown(f"**Teams Channel:** {team.get('teams_channel') or '—'}")
                    st.caption(f"Created: {format_datetime(team.get('created_at'))}")

                    # Load full team detail
                    if st.button("📋 View SDKs", key=f"view_{tid}"):
                        with st.spinner("Loading…"):
                            try:
                                detail = client.get_team(tid).get("data",{})
                                libs   = detail.get("libraries",[])
                                if libs:
                                    mandatory   = detail.get("mandatory_count",0)
                                    recommended = detail.get("recommended_count",0)
                                    st.metric("🚨 Mandatory", mandatory)
                                    rows = [{
                                        "Package":      l.get("sdk_name") or l.get("package","—"),
                                        "Platform":     l.get("platform","—"),
                                        "Current":      l.get("current_version","—"),
                                        "Latest":       l.get("latest_version","—"),
                                        "Update":       _UPDATE_BADGE.get((l.get("update_needed") or "").lower(), l.get("update_needed","—")),
                                        "Status":       l.get("status","—"),
                                        "Primary":      "⭐" if l.get("is_primary") else "",
                                    } for l in libs]
                                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                                else:
                                    st.info("No libraries assigned to this team yet.")
                            except APIError as exc:
                                st.error(f"Failed: {exc.detail}")

                    if is_admin():
                        col_e, col_d = st.columns(2)
                        with col_e.form(f"edit_team_{tid}"):
                            new_email   = st.text_input("Email",         value=team.get("team_email") or "")
                            new_channel = st.text_input("Teams Channel", value=team.get("teams_channel") or "")
                            if st.form_submit_button("💾 Update"):
                                try:
                                    client.update_team(tid, {"team_email": new_email or None, "teams_channel": new_channel or None})
                                    st.success("Updated."); st.rerun()
                                except APIError as exc:
                                    st.error(f"Failed: {exc.detail}")
                        if col_d.button("🗑️ Delete Team", key=f"del_{tid}", type="secondary"):
                            try:
                                client.delete_team(tid)
                                st.warning(f"Team '{team['team_name']}' deleted."); st.rerun()
                            except APIError as exc:
                                st.error(f"Failed: {exc.detail}")

    # ══════════════════════════════════════════════════════════════════════
    with tab_create:
        if not is_admin():
            st.info("🔒 Admin access required to create teams.")
        else:
            with st.form("create_team_form", clear_on_submit=True):
                name    = st.text_input("Team Name *", placeholder="Android Core")
                email   = st.text_input("Contact Email", placeholder="android-team@company.com")
                channel = st.text_input("Teams Channel / Webhook", placeholder="https://company.webhook.office.com/…")
                submitted = st.form_submit_button("➕ Create Team", type="primary")
            if submitted:
                if not name.strip():
                    st.error("Team name is required.")
                else:
                    try:
                        r = client.create_team({"team_name": name.strip(), "team_email": email.strip() or None, "teams_channel": channel.strip() or None})
                        st.success(f"✅ Team **{name}** created (ID: {r.get('data',{}).get('id')})")
                        st.rerun()
                    except APIError as exc:
                        st.error(f"Failed: {exc.detail}")

    # ══════════════════════════════════════════════════════════════════════
    with tab_assign:
        if not is_admin():
            st.info("🔒 Admin access required to assign libraries.")
        elif not teams:
            st.info("Create at least one team first.")
        else:
            with st.spinner("Loading libraries…"):
                try:
                    libs = client.get_libraries().get("data",{}).get("libraries",[])
                except APIError:
                    libs = []

            team_opts = {t["team_name"]: t["id"] for t in teams}
            lib_opts  = {f"[{l['id']}] {l.get('sdk_name') or l.get('package','—')} ({l.get('platform','—')})": l["id"] for l in libs}

            st.markdown("#### Bulk Assign by Platform")
            with st.form("bulk_assign_form"):
                selected_team = st.selectbox("Assign to Team *", list(team_opts.keys()))
                platform_filter = st.selectbox("Filter by Platform", ["All", "Android", "iOS", "Both"])
                is_primary = st.checkbox("Mark as Primary Owner", value=True)
                submitted_bulk = st.form_submit_button("🔗 Assign Filtered SDKs", type="primary")
            if submitted_bulk:
                tid   = team_opts[selected_team]
                batch = [l for l in libs if platform_filter == "All" or l["platform"] == platform_filter]
                done  = 0
                with st.spinner(f"Assigning {len(batch)} libraries…"):
                    for lib in batch:
                        try:
                            client.assign_library_to_team(lib["id"], tid, is_primary, username)
                            done += 1
                        except APIError:
                            pass
                st.success(f"✅ Assigned {done} libraries to **{selected_team}**.")
                st.rerun()

            st.divider()
            st.markdown("#### Single SDK Assignment")
            with st.form("single_assign_form"):
                sel_lib  = st.selectbox("SDK", list(lib_opts.keys()))
                sel_team = st.selectbox("Team",    list(team_opts.keys()))
                prim     = st.checkbox("Primary Owner", value=True)
                if st.form_submit_button("🔗 Assign", type="primary"):
                    try:
                        client.assign_library_to_team(lib_opts[sel_lib], team_opts[sel_team], prim, username)
                        st.success(f"✅ Assigned.")
                        st.rerun()
                    except APIError as exc:
                        st.error(f"Failed: {exc.detail}")

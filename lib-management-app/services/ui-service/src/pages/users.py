"""User Management page — admin only."""
from __future__ import annotations
import pandas as pd
import streamlit as st
from src.api.client import GatewayClient, APIError
from src.auth.session import get_token, get_user, is_admin
from src.utils.formatters import format_datetime


def render() -> None:
    st.title("👥 User Management")

    if not is_admin():
        st.error("🔒 Admin access required.")
        return

    client   = GatewayClient(token=get_token())
    me       = (get_user() or {}).get("username", "")

    tab_list, tab_add, tab_pwd = st.tabs(["👤 Users", "➕ Add User", "🔑 Change Password"])

    # ══════════════════════════════════════════════════════════════════════
    # Tab 1: User list
    # ══════════════════════════════════════════════════════════════════════
    with tab_list:
        with st.spinner("Loading users…"):
            try:
                users = client.get_users().get("users", [])
            except APIError as exc:
                st.error(f"Failed to load users: {exc.detail}")
                return

        st.caption(f"**{len(users)}** registered users")

        # Summary table
        df = pd.DataFrame([{
            "ID":         u.get("id"),
            "Username":   u.get("username","—"),
            "Full Name":  u.get("full_name") or "—",
            "Email":      u.get("email","—"),
            "Role":       "🔑 Admin" if u.get("role") == "admin" else "👁️ Viewer",
            "Status":     "🟢 Active" if u.get("is_active") else "🔴 Inactive",
            "Created":    format_datetime(u.get("created_at")),
            "Last Login": format_datetime(u.get("last_login")) or "Never",
        } for u in users])
        st.dataframe(df, use_container_width=True, hide_index=True,
            column_config={
                "ID":       st.column_config.NumberColumn("ID",      width="small"),
                "Username": st.column_config.TextColumn("Username",  width="medium"),
                "Role":     st.column_config.TextColumn("Role",      width="small"),
                "Status":   st.column_config.TextColumn("Status",    width="small"),
            })

        st.divider()
        st.markdown("#### Edit User")
        for u in users:
            if u.get("username") == "admin" and u.get("id") == 1:
                continue   # skip editing the bootstrap admin record inline
            uid  = u.get("id")
            uname = u.get("username","—")
            with st.expander(f"{'🔑' if u.get('role')=='admin' else '👁️'}  **{uname}**  — {u.get('email','—')}  {'🟢' if u.get('is_active') else '🔴'}"):
                with st.form(f"edit_user_{uid}"):
                    c1, c2 = st.columns(2)
                    new_full = c1.text_input("Full Name", value=u.get("full_name") or "")
                    new_email = c2.text_input("Email", value=u.get("email",""))
                    c3, c4 = st.columns(2)
                    new_role = c3.selectbox("Role", ["viewer","admin"],
                        index=0 if u.get("role") == "viewer" else 1)
                    active   = c4.toggle("Active", value=bool(u.get("is_active", True)))
                    save_btn = st.form_submit_button("💾 Save", type="primary")

                if save_btn:
                    try:
                        client.update_user(uid, {
                            "email": new_email.strip(),
                            "full_name": new_full.strip() or None,
                            "role": new_role,
                            "is_active": active,
                        })
                        st.success(f"✅ **{uname}** updated.")
                        st.rerun()
                    except APIError as exc:
                        st.error(f"Update failed: {exc.detail}")

                if u.get("username") != me:   # cannot deactivate self
                    if st.button(f"{'🔴 Deactivate' if u.get('is_active') else '🟢 Reactivate'} {uname}",
                                 key=f"deact_{uid}"):
                        try:
                            if u.get("is_active"):
                                client.deactivate_user(uid)
                                st.warning(f"**{uname}** deactivated.")
                            else:
                                client.update_user(uid, {"is_active": True})
                                st.success(f"**{uname}** reactivated.")
                            st.rerun()
                        except APIError as exc:
                            st.error(f"Failed: {exc.detail}")

    # ══════════════════════════════════════════════════════════════════════
    # Tab 2: Add new user
    # ══════════════════════════════════════════════════════════════════════
    with tab_add:
        with st.form("add_user_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            new_username  = c1.text_input("Username *", placeholder="john.doe")
            new_full_name = c2.text_input("Full Name",  placeholder="John Doe")
            c3, c4 = st.columns(2)
            new_email    = c3.text_input("Email *",    placeholder="john@company.com")
            new_role     = c4.selectbox("Role", ["viewer", "admin"])
            new_password = st.text_input("Password *", type="password",
                                         placeholder="Minimum 8 characters")
            submitted = st.form_submit_button("➕ Create User", type="primary")

        if submitted:
            if not new_username.strip() or not new_email.strip() or not new_password:
                st.error("Username, email and password are required.")
            elif len(new_password) < 8:
                st.error("Password must be at least 8 characters.")
            else:
                try:
                    client.create_user({
                        "username":  new_username.strip(),
                        "email":     new_email.strip(),
                        "password":  new_password,
                        "full_name": new_full_name.strip() or None,
                        "role":      new_role,
                    })
                    st.success(f"✅ User **{new_username}** created with role **{new_role}**.")
                    st.rerun()
                except APIError as exc:
                    st.error(f"Failed to create user: {exc.detail}")

    # ══════════════════════════════════════════════════════════════════════
    # Tab 3: Change own password
    # ══════════════════════════════════════════════════════════════════════
    with tab_pwd:
        st.markdown(f"#### Change password for **{me}**")
        with st.form("change_pwd_form", clear_on_submit=True):
            old_pwd  = st.text_input("Current Password *", type="password")
            new_pwd  = st.text_input("New Password *",     type="password",
                                      placeholder="Minimum 8 characters")
            conf_pwd = st.text_input("Confirm New Password *", type="password")
            submitted = st.form_submit_button("🔑 Change Password", type="primary")

        if submitted:
            if not old_pwd or not new_pwd or not conf_pwd:
                st.error("All fields are required.")
            elif len(new_pwd) < 8:
                st.error("New password must be at least 8 characters.")
            elif new_pwd != conf_pwd:
                st.error("New passwords do not match.")
            else:
                try:
                    client.change_password(old_pwd, new_pwd)
                    st.success("✅ Password changed successfully.")
                except APIError as exc:
                    st.error(f"Failed: {exc.detail}")

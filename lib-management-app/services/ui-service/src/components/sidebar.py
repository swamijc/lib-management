"""Sidebar navigation component."""
from __future__ import annotations
import streamlit as st
from ..auth.session import get_user, is_admin, logout

_PAGES_VIEWER = [
    ("🏠", "Dashboard",     "dashboard"),
    ("📚", "SDKs",     "libraries"),
    ("⚕️", "System Health", "health"),
]

_PAGES_ADMIN = [
    ("🏠", "Dashboard",     "dashboard"),
    ("📚", "SDKs",     "libraries"),
    ("⚙️", "Management",    "management"),
    ("🕐", "Scheduler",     "scheduler"),
    ("🔔", "Notifications", "notifications"),
    ("⚕️", "System Health", "health"),
]


def render_sidebar() -> str:
    """Render the sidebar and return the selected page key."""
    user = get_user() or {}
    pages = _PAGES_ADMIN if is_admin() else _PAGES_VIEWER

    if "current_page" not in st.session_state:
        st.session_state["current_page"] = pages[0][2]

    with st.sidebar:
        st.markdown("### 📚 SDK Manager")
        st.caption(
            f"Logged in as **{user.get('username', '')}** "
            f"({user.get('role', 'viewer')})"
        )
        st.divider()

        for icon, label, key in pages:
            if st.button(f"{icon} {label}", key=f"nav_{key}", use_container_width=True):
                st.session_state["current_page"] = key
                st.rerun()

        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            logout()
            st.rerun()

    return st.session_state.get("current_page", pages[0][2])

"""SDK Management System — Streamlit entry point.

Run with:
    streamlit run src/app.py
"""
from __future__ import annotations
import streamlit as st
from src.config import settings
from src.auth.session import is_logged_in, is_admin, get_user, logout
from src.pages import login, dashboard, libraries, management, scheduler, notifications, health
from src.pages import settings as settings_page
from src.pages import audit, governance, analytics, users as users_page
from src.pages import package_profile, teams as teams_page, reports, hitl_review


def main() -> None:
    st.set_page_config(
        page_title=settings.page_title,
        page_icon=settings.page_icon,
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # ── Not logged in: show only login page, hide sidebar navigation ──────────
    if not is_logged_in():
        pg = st.navigation(
            [st.Page(login.render, title="Sign In", icon="🔑")],
            position="hidden",
        )
        pg.run()
        return

    # ── Build page list based on role ─────────────────────────────────────────
    viewer_pages = [
        st.Page(dashboard.render,       title="Dashboard",       icon="🏠", url_path="dashboard",       default=True),
        st.Page(libraries.render,       title="SDKs",       icon="📚", url_path="libraries"),
        st.Page(package_profile.render, title="Package Profile", icon="📦", url_path="package_profile"),
        st.Page(governance.render,      title="Governance",      icon="🔄", url_path="governance"),
        st.Page(hitl_review.render,     title="HITL Review",     icon="🧑‍💼", url_path="hitl_review"),
        st.Page(health.render,          title="System Health",   icon="⚕️", url_path="health"),
    ]
    admin_only_pages = [
        st.Page(management.render,      title="Management",      icon="⚙️", url_path="management"),
        st.Page(teams_page.render,      title="Teams",           icon="👥", url_path="teams"),
        st.Page(reports.render,         title="Reports",         icon="📑", url_path="reports"),
        st.Page(scheduler.render,       title="Scheduler",       icon="🕐", url_path="scheduler"),
        st.Page(notifications.render,   title="Notifications",   icon="🔔", url_path="notifications"),
        st.Page(audit.render,           title="Audit Trail",     icon="📋", url_path="audit"),
        st.Page(analytics.render,       title="Analytics",       icon="📊", url_path="analytics"),
        st.Page(users_page.render,      title="Users",           icon="👤", url_path="users"),
        st.Page(settings_page.render,   title="Settings",        icon="🤖", url_path="settings"),
    ]

    pages = viewer_pages + (admin_only_pages if is_admin() else [])
    pg = st.navigation(pages)

    # ── Sidebar: user info + logout ───────────────────────────────────────────
    with st.sidebar:
        user = get_user() or {}
        st.markdown(f"👤 **{user.get('username', '')}**  `{user.get('role', 'viewer')}`")
        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            logout()
            st.rerun()

    pg.run()


if __name__ == "__main__":
    main()


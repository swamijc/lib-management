"""System Health page — aggregate status of all backend services."""
from __future__ import annotations
import streamlit as st
from src.api.client import GatewayClient, APIError
from src.auth.session import get_token


_STATUS_COLOR = {
    "healthy":    "✅",
    "degraded":   "⚠️",
    "unreachable": "❌",
}


def render() -> None:
    st.title("⚕️ System Health")

    client = GatewayClient(token=get_token())

    if st.button("🔄 Refresh"):
        st.rerun()

    # ── Gateway own health ────────────────────────────────────────────────────
    try:
        gw = client.get_health()
        st.success(f"API Gateway: {gw.get('status', 'unknown')}")
    except APIError as exc:
        st.error(f"API Gateway unreachable: {exc.detail}")
        return

    # ── Backend services ──────────────────────────────────────────────────────
    st.subheader("Backend Services")
    try:
        data = client.get_services_health()
        services = data.get("services", [])
        overall = data.get("overall", "unknown")

        overall_icon = _STATUS_COLOR.get(overall, "❓")
        st.markdown(f"**Overall:** {overall_icon} {overall.title()}")
        st.divider()

        cols = st.columns(3)
        for i, svc in enumerate(services):
            icon = _STATUS_COLOR.get(svc.get("status", ""), "❓")
            with cols[i % 3]:
                st.metric(
                    label=svc.get("service", "—"),
                    value=f"{icon} {svc.get('status', '—').title()}",
                )
                if svc.get("error"):
                    st.caption(f"⚠️ {svc['error']}")

    except APIError as exc:
        st.error(f"Could not retrieve service health: {exc.detail}")

"""Login page."""
from __future__ import annotations
import streamlit as st
from src.api.client import GatewayClient, APIError
from src.auth.session import login as session_login


def render() -> None:
    st.title("📚 SDK Management System")
    st.subheader("Sign In")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login", use_container_width=True)

    if submitted:
        if not username or not password:
            st.error("Username and password are required.")
            return
        try:
            client = GatewayClient()
            token_data = client.authenticate(username, password)
            authed_client = GatewayClient(token=token_data["access_token"])
            user_info = authed_client.get_me()
            session_login(token_data["access_token"], user_info)
            st.rerun()
        except APIError as exc:
            st.error(f"Login failed: {exc.detail}")

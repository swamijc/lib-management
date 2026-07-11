"""Session state helpers — wraps Streamlit session_state."""
from __future__ import annotations
from typing import Optional
import streamlit as st

_TOKEN_KEY = "jwt_token"
_USER_KEY = "current_user"


def is_logged_in() -> bool:
    return bool(st.session_state.get(_TOKEN_KEY))


def get_token() -> Optional[str]:
    return st.session_state.get(_TOKEN_KEY)


def get_user() -> Optional[dict]:
    return st.session_state.get(_USER_KEY)


def login(token: str, user_info: dict) -> None:
    st.session_state[_TOKEN_KEY] = token
    st.session_state[_USER_KEY] = user_info


def logout() -> None:
    st.session_state.pop(_TOKEN_KEY, None)
    st.session_state.pop(_USER_KEY, None)


def is_admin() -> bool:
    user = get_user()
    return user is not None and user.get("role") == "admin"

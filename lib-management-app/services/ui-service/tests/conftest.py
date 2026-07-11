"""
Inject a mock `streamlit` module before any src imports so that
modules using `import streamlit as st` work in unit tests.
"""
import sys
from unittest.mock import MagicMock
import pytest


class _SessionState(dict):
    """dict subclass that also supports attribute-style access (mirrors st.session_state)."""

    def __getattr__(self, key: str):
        if key.startswith("_"):
            return super().__getattribute__(key)
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __setattr__(self, key: str, value):
        if key.startswith("_"):
            super().__setattr__(key, value)
        else:
            self[key] = value


# Build the mock once and attach a real SessionState instance.
_mock_st = MagicMock(name="streamlit")
_mock_st.session_state = _SessionState()

# Register before any src.* imports happen.
sys.modules["streamlit"] = _mock_st


@pytest.fixture(autouse=True)
def clear_session_state():
    """Reset session state between every test."""
    _mock_st.session_state.clear()
    yield
    _mock_st.session_state.clear()

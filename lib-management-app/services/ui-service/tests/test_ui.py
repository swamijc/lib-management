"""
Unit tests for ui-service.

Coverage:
  - src/utils/formatters.py   (pure functions — no mocking required)
  - src/auth/session.py       (streamlit session_state — mocked via conftest)
  - src/api/client.py         (httpx — mocked with unittest.mock)
"""
from __future__ import annotations
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import pytest
import httpx

# ── formatters module is pure Python; import directly ─────────────────────────
from src.utils.formatters import (
    format_version_status,
    format_upgrade_decision,
    format_datetime,
    format_registry,
    format_pipeline_status,
)

# ── session module depends on mocked `streamlit` (injected in conftest) ───────
from src.auth.session import (
    is_logged_in,
    get_token,
    get_user,
    login,
    logout,
    is_admin,
)

# ── API client ────────────────────────────────────────────────────────────────
from src.api.client import GatewayClient, APIError


# ═══════════════════════════════════════════════════════════════════════════════
# Formatter tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestFormatVersionStatus:
    def test_up_to_date_shows_check(self):
        result = format_version_status("up_to_date")
        assert "✅" in result
        assert "Up To Date" in result

    def test_major_update_shows_red(self):
        result = format_version_status("major_update")
        assert "🔴" in result

    def test_patch_update_shows_blue(self):
        result = format_version_status("patch_update")
        assert "🔵" in result

    def test_unknown_status_shows_question(self):
        result = format_version_status("something_new")
        assert "❓" in result


class TestFormatUpgradeDecision:
    def test_upgrade_shows_arrow(self):
        result = format_upgrade_decision("upgrade")
        assert "⬆️" in result

    def test_none_returns_dash(self):
        assert format_upgrade_decision(None) == "—"

    def test_hold_shows_pause(self):
        result = format_upgrade_decision("hold")
        assert "⏸️" in result


class TestFormatDatetime:
    def test_none_returns_dash(self):
        assert format_datetime(None) == "—"

    def test_iso_string_parsed(self):
        result = format_datetime("2025-03-15T14:30:00")
        assert "2025-03-15" in result
        assert "14:30" in result

    def test_z_suffix_parsed(self):
        result = format_datetime("2025-01-01T00:00:00Z")
        assert "2025-01-01" in result

    def test_datetime_object(self):
        dt = datetime(2024, 6, 20, 9, 0, tzinfo=timezone.utc)
        result = format_datetime(dt)
        assert "2024-06-20" in result


class TestFormatRegistry:
    def test_maven_shows_coffee(self):
        assert "☕" in format_registry("maven")

    def test_github_shows_octopus(self):
        assert "🐙" in format_registry("github")

    def test_none_returns_dash(self):
        assert format_registry(None) == "—"

    def test_unknown_registry_returned_as_is(self):
        assert format_registry("npm") == "npm"


class TestFormatPipelineStatus:
    def test_completed_shows_check(self):
        assert "✅" in format_pipeline_status("completed")

    def test_failed_shows_cross(self):
        assert "❌" in format_pipeline_status("failed")

    def test_running_shows_arrows(self):
        assert "🔄" in format_pipeline_status("running")


# ═══════════════════════════════════════════════════════════════════════════════
# Session tests  (st.session_state is the _SessionState dict from conftest)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSession:
    def test_initially_not_logged_in(self):
        assert is_logged_in() is False

    def test_get_token_initially_none(self):
        assert get_token() is None

    def test_login_sets_logged_in(self):
        login("tok123", {"username": "alice", "role": "admin"})
        assert is_logged_in() is True

    def test_get_token_after_login(self):
        login("tok456", {"username": "bob", "role": "viewer"})
        assert get_token() == "tok456"

    def test_get_user_after_login(self):
        login("tok789", {"username": "charlie", "role": "admin"})
        user = get_user()
        assert user is not None
        assert user["username"] == "charlie"

    def test_logout_clears_state(self):
        login("tok999", {"username": "dave", "role": "viewer"})
        logout()
        assert is_logged_in() is False
        assert get_token() is None
        assert get_user() is None

    def test_is_admin_true_for_admin_role(self):
        login("tok", {"username": "admin", "role": "admin"})
        assert is_admin() is True

    def test_is_admin_false_for_viewer(self):
        login("tok", {"username": "viewer", "role": "viewer"})
        assert is_admin() is False

    def test_is_admin_false_when_logged_out(self):
        assert is_admin() is False


# ═══════════════════════════════════════════════════════════════════════════════
# API client tests  (httpx calls mocked)
# ═══════════════════════════════════════════════════════════════════════════════

def _mock_response(status_code: int, json_data: dict) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    return resp


class TestGatewayClientAuth:
    def test_authenticate_success(self):
        mock_resp = _mock_response(200, {"access_token": "abc", "token_type": "bearer"})
        with patch("httpx.post", return_value=mock_resp) as mock_post:
            client = GatewayClient()
            result = client.authenticate("admin", "pass")
        assert result["access_token"] == "abc"
        mock_post.assert_called_once()

    def test_authenticate_wrong_password_raises(self):
        mock_resp = _mock_response(401, {"detail": "Incorrect credentials"})
        with patch("httpx.post", return_value=mock_resp):
            client = GatewayClient()
            with pytest.raises(APIError) as exc_info:
                client.authenticate("admin", "wrong")
        assert exc_info.value.status_code == 401

    def test_authenticate_network_error_raises(self):
        with patch("httpx.post", side_effect=httpx.ConnectError("refused")):
            client = GatewayClient()
            with pytest.raises(APIError) as exc_info:
                client.authenticate("admin", "pass")
        assert exc_info.value.status_code == 503


class TestGatewayClientLibraries:
    def test_get_libraries_success(self):
        payload = {"data": {"libraries": [{"id": 1, "name": "retrofit"}]}}
        mock_resp = _mock_response(200, payload)
        with patch("httpx.request", return_value=mock_resp):
            client = GatewayClient(token="tok")
            result = client.get_libraries()
        assert result["data"]["libraries"][0]["name"] == "retrofit"

    def test_get_libraries_sends_auth_header(self):
        mock_resp = _mock_response(200, {"data": {"libraries": []}})
        with patch("httpx.request", return_value=mock_resp) as mock_req:
            client = GatewayClient(token="mytoken")
            client.get_libraries()
        _, call_kwargs = mock_req.call_args
        headers = call_kwargs.get("headers") or mock_req.call_args[1].get("headers", {})
        # Verify token was sent (call_args positional or keyword)
        all_args = str(mock_req.call_args)
        assert "mytoken" in all_args

    def test_create_library_posts_payload(self):
        mock_resp = _mock_response(201, {"data": {"id": 5, "name": "okhttp"}})
        with patch("httpx.request", return_value=mock_resp) as mock_req:
            client = GatewayClient(token="tok")
            result = client.create_library({"name": "okhttp", "current_version": "4.0.0"})
        assert result["data"]["name"] == "okhttp"
        called_method = mock_req.call_args[0][0]
        assert called_method == "POST"

    def test_delete_library_sends_delete(self):
        mock_resp = _mock_response(204, {})
        mock_resp.status_code = 204
        mock_resp.json.return_value = {}
        with patch("httpx.request", return_value=mock_resp) as mock_req:
            client = GatewayClient(token="tok")
            client.delete_library(7)
        called_method = mock_req.call_args[0][0]
        assert called_method == "DELETE"

    def test_4xx_response_raises_api_error(self):
        mock_resp = _mock_response(404, {"detail": "not found"})
        with patch("httpx.request", return_value=mock_resp):
            client = GatewayClient(token="tok")
            with pytest.raises(APIError) as exc_info:
                client.get_library(999)
        assert exc_info.value.status_code == 404

    def test_connection_error_raises_503(self):
        with patch("httpx.request", side_effect=httpx.ConnectError("no route")):
            client = GatewayClient(token="tok")
            with pytest.raises(APIError) as exc_info:
                client.get_libraries()
        assert exc_info.value.status_code == 503


class TestGatewayClientHealth:
    def test_get_health(self):
        mock_resp = _mock_response(200, {"status": "healthy"})
        with patch("httpx.request", return_value=mock_resp):
            client = GatewayClient()
            result = client.get_health()
        assert result["status"] == "healthy"

    def test_get_services_health(self):
        payload = {"overall": "healthy", "services": [{"service": "svc", "status": "healthy"}]}
        mock_resp = _mock_response(200, payload)
        with patch("httpx.request", return_value=mock_resp):
            client = GatewayClient()
            result = client.get_services_health()
        assert result["overall"] == "healthy"
        assert len(result["services"]) == 1

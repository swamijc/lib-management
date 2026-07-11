"""HTTP client for the API Gateway (synchronous httpx)."""
from __future__ import annotations
from typing import Any
import httpx

from ..config import settings


class APIError(Exception):
    """Raised when the API gateway returns an error status."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class GatewayClient:
    """Thin synchronous wrapper around the API gateway endpoints."""

    def __init__(self, token: str | None = None, timeout: float | None = None) -> None:
        self._token = token
        self._timeout = timeout if timeout is not None else settings.request_timeout
        self._base = settings.api_gateway_url

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self._base}{path}"
        try:
            resp = httpx.request(
                method, url,
                headers=self._headers(),
                timeout=self._timeout,
                **kwargs,
            )
        except httpx.RequestError as exc:
            raise APIError(503, f"Gateway unreachable: {exc}") from exc
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise APIError(resp.status_code, detail)
        return resp.json()

    # ── Auth ──────────────────────────────────────────────────────────────────

    def authenticate(self, username: str, password: str) -> dict:
        """POST /auth/token — returns {access_token, token_type}."""
        try:
            resp = httpx.post(
                f"{self._base}/auth/token",
                data={"username": username, "password": password},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self._timeout,
            )
        except httpx.RequestError as exc:
            raise APIError(503, str(exc)) from exc
        if resp.status_code != 200:
            try:
                detail = resp.json().get("detail", "Login failed")
            except Exception:
                detail = resp.text
            raise APIError(resp.status_code, detail)
        return resp.json()

    def get_me(self) -> dict:
        return self._request("GET", "/auth/me")

    # ── Libraries ─────────────────────────────────────────────────────────────

    def get_libraries(self) -> dict:
        return self._request("GET", "/api/v1/libraries", params={"limit": 1000})

    def get_library(self, library_id: int) -> dict:
        return self._request("GET", f"/api/v1/libraries/{library_id}")

    def create_library(self, payload: dict) -> dict:
        return self._request("POST", "/api/v1/libraries", json=payload)

    def update_library(self, library_id: int, payload: dict) -> dict:
        return self._request("PUT", f"/api/v1/libraries/{library_id}", json=payload)

    def delete_library(self, library_id: int) -> None:
        self._request("DELETE", f"/api/v1/libraries/{library_id}")

    # ── Scraper ───────────────────────────────────────────────────────────────

    def scrape_library(self, payload: dict) -> dict:
        return self._request("POST", "/api/v1/scrape", json=payload)

    # ── Comparisons ───────────────────────────────────────────────────────────

    def get_comparisons(self) -> dict:
        return self._request("GET", "/api/v1/comparisons")

    def run_comparison(self, payload: dict) -> dict:
        return self._request("POST", "/api/v1/compare", json=payload)

    # ── Recommendations ───────────────────────────────────────────────────────

    def get_recommendations(self) -> dict:
        return self._request("GET", "/api/v1/recommendations")

    def generate_recommendation(self, payload: dict) -> dict:
        return self._request("POST", "/api/v1/recommendations/generate", json=payload)

    # ── Scheduler ─────────────────────────────────────────────────────────────

    def get_schedule(self) -> dict:
        return self._request("GET", "/api/v1/schedule")

    def update_schedule(self, payload: dict) -> dict:
        return self._request("PUT", "/api/v1/schedule", json=payload)

    def trigger_run(self) -> dict:
        return self._request("POST", "/api/v1/run/now")

    def get_runs(self) -> dict:
        return self._request("GET", "/api/v1/runs")

    def get_run(self, run_id: str) -> dict:
        return self._request("GET", f"/api/v1/runs/{run_id}")

    def get_pipeline_run_detail(self, run_id: str) -> dict:
        return self._request("GET", f"/api/v1/pipeline-runs/{run_id}")

    def get_version_history(self, library_id: int) -> dict:
        return self._request("GET", f"/api/v1/version-history/{library_id}")

    # ── Notifications ─────────────────────────────────────────────────────────

    def get_notifications_log(self) -> dict:
        return self._request("GET", "/api/v1/notifications")

    # ── Health ────────────────────────────────────────────────────────────────

    def get_health(self) -> dict:
        return self._request("GET", "/health")

    def get_services_health(self) -> dict:
        return self._request("GET", "/health/services")

    # ── Settings ──────────────────────────────────────────────────────────────

    def get_llm_config(self) -> dict:
        return self._request("GET", "/api/v1/settings/llm")

    def update_llm_config(self, payload: dict) -> dict:
        return self._request("PUT", "/api/v1/settings/llm", json=payload)

    def get_prompts(self) -> dict:
        return self._request("GET", "/api/v1/settings/prompts")

    def upsert_prompt(self, key: str, payload: dict) -> dict:
        return self._request("PUT", f"/api/v1/settings/prompts/{key}", json=payload)

    def get_app_settings(self) -> dict:
        return self._request("GET", "/api/v1/settings/app")

    def update_app_setting(self, key: str, value: str, updated_by: str | None = None) -> dict:
        return self._request("PUT", f"/api/v1/settings/app/{key}", json={"value": value, "updated_by": updated_by})

    def test_llm(self, package: str = "retrofit", platform: str = "Android",
                 current_version: str = "2.9.0", latest_version: str = "3.0.0") -> dict:
        return self._request("POST", "/api/v1/recommendations/test-llm", json={
            "package": package, "platform": platform,
            "current_version": current_version, "latest_version": latest_version,
        })

    # ── Audit Trail ───────────────────────────────────────────────────────────

    def get_audit_log(self, library_id: int | None = None, updated_by: str | None = None,
                      date_from: str | None = None, date_to: str | None = None,
                      limit: int = 200) -> dict:
        params: dict = {"limit": limit}
        if library_id:  params["library_id"] = library_id
        if updated_by:  params["updated_by"] = updated_by
        if date_from:   params["date_from"] = date_from
        if date_to:     params["date_to"] = date_to
        return self._request("GET", "/api/v1/audit-log", params=params)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def get_lifecycles(self, status: str | None = None, platform: str | None = None) -> dict:
        params: dict = {}
        if status:   params["status"] = status
        if platform: params["platform"] = platform
        return self._request("GET", "/api/v1/lifecycle", params=params)

    def get_library_lifecycle(self, library_id: int) -> dict:
        return self._request("GET", f"/api/v1/lifecycle/{library_id}")

    def init_lifecycle(self, library_id: int, actioned_by: str,
                       recommendation_id: int | None = None) -> dict:
        return self._request("POST", "/api/v1/lifecycle", json={
            "library_id": library_id, "actioned_by": actioned_by,
            "recommendation_id": recommendation_id,
        })

    def update_lifecycle(self, lifecycle_id: int, payload: dict) -> dict:
        return self._request("PUT", f"/api/v1/lifecycle/{lifecycle_id}", json=payload)

    def complete_lifecycle(self, lifecycle_id: int, completed_version: str,
                           actioned_by: str, pr_url: str | None = None,
                           reason: str | None = None) -> dict:
        return self._request("PUT", f"/api/v1/lifecycle/{lifecycle_id}/complete", json={
            "completed_version": completed_version, "actioned_by": actioned_by,
            "pr_url": pr_url, "reason": reason,
        })

    # ── LLM Analytics ─────────────────────────────────────────────────────────

    def get_llm_usage(self, limit: int = 100) -> dict:
        return self._request("GET", "/api/v1/llm/usage", params={"limit": limit})

    # ── User Management ───────────────────────────────────────────────────────

    def get_users(self) -> dict:
        return self._request("GET", "/auth/users")

    def create_user(self, payload: dict) -> dict:
        return self._request("POST", "/auth/users", json=payload)

    def update_user(self, user_id: int, payload: dict) -> dict:
        return self._request("PUT", f"/auth/users/{user_id}", json=payload)

    def deactivate_user(self, user_id: int) -> dict:
        return self._request("DELETE", f"/auth/users/{user_id}")

    def change_password(self, old_password: str, new_password: str) -> dict:
        return self._request("POST", "/auth/change-password", json={
            "old_password": old_password, "new_password": new_password,
        })

    # ── CVE scanning ──────────────────────────────────────────────────────────

    def scan_cve(self, library_id: int, force_refresh: bool = False) -> dict:
        return self._request("GET", f"/api/v1/cve/{library_id}",
                             params={"force_refresh": str(force_refresh).lower()})

    def get_cve_cache(self, platform: str | None = None, has_vulns: bool | None = None) -> dict:
        params: dict = {}
        if platform:   params["platform"]  = platform
        if has_vulns is not None: params["has_vulns"] = str(has_vulns).lower()
        return self._request("GET", "/api/v1/cve", params=params)

    # ── Teams / ownership ─────────────────────────────────────────────────────

    def get_teams(self) -> dict:
        return self._request("GET", "/api/v1/teams")

    def get_team(self, team_id: int) -> dict:
        return self._request("GET", f"/api/v1/teams/{team_id}")

    def create_team(self, payload: dict) -> dict:
        return self._request("POST", "/api/v1/teams", json=payload)

    def update_team(self, team_id: int, payload: dict) -> dict:
        return self._request("PUT", f"/api/v1/teams/{team_id}", json=payload)

    def delete_team(self, team_id: int) -> dict:
        return self._request("DELETE", f"/api/v1/teams/{team_id}")

    def assign_library_to_team(self, library_id: int, team_id: int,
                                is_primary: bool, assigned_by: str) -> dict:
        return self._request("POST", "/api/v1/teams/assign", json={
            "library_id": library_id, "team_id": team_id,
            "is_primary": is_primary, "assigned_by": assigned_by,
        })

    def unassign_library(self, library_id: int, team_id: int) -> dict:
        return self._request("DELETE", f"/api/v1/teams/assign/{library_id}/{team_id}")

    def get_library_teams(self, library_id: int) -> dict:
        return self._request("GET", f"/api/v1/teams/library/{library_id}")

    # ── SLA ───────────────────────────────────────────────────────────────────

    def get_sla_overdue(self, platform: str | None = None) -> dict:
        params = {"platform": platform} if platform else {}
        return self._request("GET", "/api/v1/sla/overdue", params=params)

    def get_sla_approaching(self, days_ahead: int = 30) -> dict:
        return self._request("GET", "/api/v1/sla/approaching", params={"days_ahead": days_ahead})

    def get_sla_summary(self) -> dict:
        return self._request("GET", "/api/v1/sla/summary")

    def get_release_notes(self, library_id: int) -> dict:
        return self._request("GET", f"/api/v1/sla/release-notes/{library_id}")

    # ── HITL Review ───────────────────────────────────────────────────────────

    def get_pending_review(self) -> dict:
        return self._request("GET", "/api/v1/lifecycle/pending/review")

    def approve_no_action(self, lifecycle_id: int, actioned_by: str) -> dict:
        return self._request("PUT", f"/api/v1/lifecycle/{lifecycle_id}/approve-no-action",
                             json={"actioned_by": actioned_by})

    def reject_upgrade(self, lifecycle_id: int, actioned_by: str, reason: str = "") -> dict:
        return self._request("PUT", f"/api/v1/lifecycle/{lifecycle_id}/reject",
                             json={"actioned_by": actioned_by, "reason": reason})

    def send_hitl_notification(self, approved_libs: list[dict],
                               smtp_override: dict | None = None,
                               teams_webhook: str | None = None,
                               recipients: list[str] | None = None) -> dict:
        payload: dict = {
            "libraries": approved_libs,
            "subject": "SDK Upgrade Approval — Human-Reviewed Recommendations",
            "force_send": True,
        }
        if smtp_override:   payload["smtp_override"] = smtp_override
        if teams_webhook:   payload["teams_webhook_override"] = teams_webhook
        if recipients:      payload["recipients"] = recipients
        return self._request("POST", "/api/v1/notify/both", json=payload)

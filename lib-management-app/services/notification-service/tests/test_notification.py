"""
Tests for notification-service — channels mocked, no real SMTP/Teams calls.
"""
from __future__ import annotations
from unittest.mock import AsyncMock, patch
import pytest

from src.models.schemas import NotificationStatus
from src.services.notification_service import NotificationService, _sent_hashes


# ── Shared fixture data ───────────────────────────────────────────────────────

_LIBS = [
    {
        "library_id": 1, "package": "androidx.core:core-ktx", "platform": "Android",
        "current_version": "1.12.0", "latest_version": "1.15.0",
        "update_needed": "Mandatory", "library_status": "Active",
        "upgrade_recommended": "Yes",
        "recommendation_summary": "Upgrade recommended due to security fix.",
    },
    {
        "library_id": 2, "package": "Alamofire", "platform": "iOS",
        "current_version": "5.9.1", "latest_version": "5.12.0",
        "update_needed": "Recommended", "library_status": "Active",
        "upgrade_recommended": "Yes",
    },
    {
        "library_id": 3, "package": "com.google.firebase:firebase-bom", "platform": "Android",
        "current_version": "33.5.0", "latest_version": "33.5.0",
        "update_needed": "None", "library_status": "Active",
        "upgrade_recommended": "Sufficient",
    },
    {
        "library_id": 4, "package": "JLRoutes", "platform": "iOS",
        "current_version": "2.1", "latest_version": "2.1",
        "update_needed": "Mandatory", "library_status": "Deprecated",
        "upgrade_recommended": "Yes",
        "recommendation_summary": "Deprecated — migrate away.",
    },
    {
        "library_id": 5, "package": "ACI-OPPWAMobile", "platform": "iOS",
        "current_version": "7.2.3", "latest_version": "7.11.0",
        "update_needed": "Mandatory", "library_status": "Active",
        "upgrade_recommended": "Yes",
        "alert_priority": "Critical",
        "deadline_date": "2026-07-15",
        "deadline_notes": "Mastercard certificate expires 15 July 2026.",
    },
]

_REQ = {"libraries": _LIBS, "subject": "Test Report", "force_send": True}


# ── Template tests (no HTTP) ──────────────────────────────────────────────────

class TestTemplates:
    def test_email_html_renders_without_error(self):
        from src.templates.notification_templates import render_email_html
        from src.services.notification_service import NotificationService
        from src.models.schemas import LibrarySummaryItem
        libs = [LibrarySummaryItem(**l) for l in _LIBS]
        ctx = NotificationService._build_context(libs)
        html = render_email_html(ctx)
        assert "SDK Management" in html
        assert "androidx.core:core-ktx" in html
        assert "Deprecated" in html
        assert "CRITICAL" in html  # ACI-OPPWAMobile critical alert

    def test_teams_card_renders_without_error(self):
        from src.templates.notification_templates import render_teams_card
        from src.services.notification_service import NotificationService
        from src.models.schemas import LibrarySummaryItem
        libs = [LibrarySummaryItem(**l) for l in _LIBS]
        ctx = NotificationService._build_context(libs)
        card = render_teams_card(ctx)
        assert card["type"] == "message"
        assert "attachments" in card


# ── Dedup tests (no HTTP) ────────────────────────────────────────────────────

class TestDedup:
    def setup_method(self):
        _sent_hashes.clear()

    def test_same_payload_detected_as_duplicate(self):
        from src.models.schemas import LibrarySummaryItem
        svc = NotificationService()
        libs = [LibrarySummaryItem(**l) for l in _LIBS]
        h = svc._compute_hash(libs)
        assert not svc._is_duplicate(h)
        svc._record_hash(h)
        assert svc._is_duplicate(h)

    def test_different_payload_not_duplicate(self):
        from src.models.schemas import LibrarySummaryItem
        svc = NotificationService()
        libs1 = [LibrarySummaryItem(**_LIBS[0])]
        libs2 = [LibrarySummaryItem(**_LIBS[1])]
        h1 = svc._compute_hash(libs1)
        h2 = svc._compute_hash(libs2)
        svc._record_hash(h1)
        assert not svc._is_duplicate(h2)


# ── Router integration tests ──────────────────────────────────────────────────

class TestHealthRouter:
    @pytest.mark.asyncio
    async def test_health_returns_200(self, test_client):
        resp = await test_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["email_enabled"] is False   # not configured in test env
        assert data["teams_enabled"] is False


class TestEmailRouter:
    @pytest.mark.asyncio
    async def test_email_not_configured_returns_failed(self, test_client):
        """Email channel is not configured in test env → FAILED status."""
        resp = await test_client.post("/api/v1/notify/email", json=_REQ)
        assert resp.status_code == 200
        result = resp.json()["data"]
        assert result["results"][0]["status"] == "failed"
        assert "not configured" in result["results"][0]["message"]

    @pytest.mark.asyncio
    async def test_email_send_success_when_mocked(self, test_client):
        """Patch send_email at the service layer — verify SENT status returned."""
        with patch(
            "src.services.notification_service.send_email",
            new_callable=AsyncMock,
        ):
            resp = await test_client.post("/api/v1/notify/email", json=_REQ)
        assert resp.status_code == 200
        assert resp.json()["data"]["results"][0]["status"] == "sent"


class TestTeamsRouter:
    @pytest.mark.asyncio
    async def test_teams_not_configured_returns_failed(self, test_client):
        resp = await test_client.post("/api/v1/notify/teams", json=_REQ)
        assert resp.status_code == 200
        assert resp.json()["data"]["results"][0]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_teams_send_success_when_mocked(self, test_client):
        """Patch send_teams at the service layer — verify SENT status returned."""
        with patch(
            "src.services.notification_service.send_teams",
            new_callable=AsyncMock,
        ):
            resp = await test_client.post("/api/v1/notify/teams", json=_REQ)
        assert resp.status_code == 200
        assert resp.json()["data"]["results"][0]["status"] == "sent"


class TestBothRouter:
    @pytest.mark.asyncio
    async def test_both_returns_two_channel_results(self, test_client):
        resp = await test_client.post("/api/v1/notify/both", json=_REQ)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["results"]) == 2
        channels = {r["channel"] for r in data["results"]}
        assert "email" in channels
        assert "teams" in channels


class TestDedupRouter:
    def setup_method(self):
        _sent_hashes.clear()

    @pytest.mark.asyncio
    async def test_second_call_skipped_by_dedup(self, test_client):
        req = {**_REQ, "force_send": False}

        # First call — channels not configured → FAILED but hash NOT recorded
        resp1 = await test_client.post("/api/v1/notify/email", json=req)
        assert resp1.json()["data"]["skipped_by_dedup"] is False

        # Manually record the hash to simulate a prior successful send
        from src.models.schemas import LibrarySummaryItem
        svc = NotificationService()
        libs = [LibrarySummaryItem(**l) for l in _LIBS]
        svc._record_hash(svc._compute_hash(libs))

        # Second call — same payload, hash found → skipped
        resp2 = await test_client.post("/api/v1/notify/email", json=req)
        assert resp2.json()["data"]["skipped_by_dedup"] is True


class TestNotificationsLog:
    @pytest.mark.asyncio
    async def test_list_notifications_returns_list(self, test_client):
        resp = await test_client.get("/api/v1/notifications")
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

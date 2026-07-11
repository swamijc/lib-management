"""
Integration tests for comparison-service HTTP endpoints.
No external HTTP calls (no mocking needed — service is self-contained).
"""
from __future__ import annotations
import pytest


class TestHealthRouter:
    @pytest.mark.asyncio
    async def test_health_returns_200(self, test_client):
        resp = await test_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


class TestCompareRouter:
    _PAYLOAD = {
        "library_id": 1,
        "package": "androidx.core:core-ktx",
        "platform": "Android",
        "current_version": "1.12.0",
        "latest_version": "1.15.0",
        "update_needed": "Mandatory",
    }

    @pytest.mark.asyncio
    async def test_compare_one_returns_200(self, test_client):
        resp = await test_client.post("/api/v1/compare", json=self._PAYLOAD)
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["version_status"] == "newer"
        assert data["new_version_released"] is True
        assert data["minor_bump"] is True

    @pytest.mark.asyncio
    async def test_compare_same_version(self, test_client):
        payload = {**self._PAYLOAD, "current_version": "1.15.0"}
        resp = await test_client.post("/api/v1/compare", json=payload)
        data = resp.json()["data"]
        assert data["version_status"] == "same"
        assert data["new_version_released"] is False

    @pytest.mark.asyncio
    async def test_compare_major_bump(self, test_client):
        payload = {**self._PAYLOAD, "current_version": "1.0.0", "latest_version": "2.0.0"}
        resp = await test_client.post("/api/v1/compare", json=payload)
        data = resp.json()["data"]
        assert data["version_status"] == "newer"
        assert data["major_bump"] is True

    @pytest.mark.asyncio
    async def test_compare_unknown_version_flags_manual_review(self, test_client):
        payload = {**self._PAYLOAD, "current_version": "ViaSPM", "latest_version": "6.17.9"}
        resp = await test_client.post("/api/v1/compare", json=payload)
        data = resp.json()["data"]
        assert data["version_status"] == "unknown"
        assert data["needs_manual_review"] is True


class TestBatchCompareRouter:
    @pytest.mark.asyncio
    async def test_batch_compare_returns_summary(self, test_client):
        payload = {"libraries": [
            {"library_id": 1, "package": "com.a:a", "platform": "Android",
             "current_version": "1.0.0", "latest_version": "2.0.0"},
            {"library_id": 2, "package": "com.b:b", "platform": "Android",
             "current_version": "3.0.0", "latest_version": "3.0.0"},
            {"library_id": 3, "package": "Alamofire", "platform": "iOS",
             "current_version": "ViaSPM", "latest_version": "5.12.0"},
        ]}
        resp = await test_client.post("/api/v1/compare/batch", json=payload)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 3
        assert data["newer_count"] == 1
        assert data["same_count"] == 1
        assert data["unknown_count"] == 1
        assert len(data["results"]) == 3

    @pytest.mark.asyncio
    async def test_batch_results_cached_for_get(self, test_client):
        payload = {"libraries": [
            {"library_id": 42, "package": "com.test:lib", "platform": "Android",
             "current_version": "1.0.0", "latest_version": "1.1.0"},
        ]}
        await test_client.post("/api/v1/compare/batch", json=payload)
        resp = await test_client.get("/api/v1/comparisons/42")
        assert resp.status_code == 200
        assert resp.json()["data"]["library_id"] == 42

    @pytest.mark.asyncio
    async def test_get_comparison_not_found_returns_404(self, test_client):
        resp = await test_client.get("/api/v1/comparisons/99999")
        assert resp.status_code == 404


class TestListComparisonsRouter:
    @pytest.mark.asyncio
    async def test_list_comparisons_returns_list(self, test_client):
        resp = await test_client.get("/api/v1/comparisons")
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

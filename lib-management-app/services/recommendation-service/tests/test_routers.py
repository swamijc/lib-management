"""
Integration tests for recommendation-service HTTP endpoints.
LLM is disabled (env vars set in conftest) → all generation uses rule-based path.
"""
from __future__ import annotations
import pytest


_LIB = {
    "library_id": 1,
    "package": "com.google.firebase:firebase-bom",
    "platform": "Android",
    "current_version": "33.1.0",
    "latest_version": "33.5.0",
    "update_needed": "Mandatory",
    "library_status": "Active",
    "new_version_released": True,
    "version_status": "newer",
}


class TestHealthRouter:
    @pytest.mark.asyncio
    async def test_health_returns_200(self, test_client):
        resp = await test_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["llm_enabled"] is False

    @pytest.mark.asyncio
    async def test_health_shows_rule_based_when_llm_disabled(self, test_client):
        resp = await test_client.get("/health")
        assert "rule-based" in resp.json()["llm_provider"]


class TestGenerateOne:
    @pytest.mark.asyncio
    async def test_generate_one_returns_200(self, test_client):
        resp = await test_client.post(
            f"/api/v1/recommendations/generate/{_LIB['library_id']}",
            json=_LIB,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["upgrade_recommended"] == "Yes"
        assert data["generator_used"] == "rule_based"
        assert data["recommendation_summary"]

    @pytest.mark.asyncio
    async def test_generate_one_deprecated_library(self, test_client):
        payload = {**_LIB, "library_id": 10, "library_status": "Deprecated"}
        resp = await test_client.post("/api/v1/recommendations/generate/10", json=payload)
        data = resp.json()["data"]
        assert data["upgrade_recommended"] == "Yes"
        assert data["upgrade_pros"]

    @pytest.mark.asyncio
    async def test_generate_one_up_to_date_returns_sufficient(self, test_client):
        payload = {
            **_LIB, "library_id": 20,
            "current_version": "33.5.0",
            "latest_version": "33.5.0",
            "new_version_released": False,
        }
        resp = await test_client.post("/api/v1/recommendations/generate/20", json=payload)
        assert resp.json()["data"]["upgrade_recommended"] == "Sufficient"


class TestBatchGenerate:
    @pytest.mark.asyncio
    async def test_batch_returns_summary_counts(self, test_client):
        payload = {"libraries": [
            {**_LIB, "library_id": 101},
            {**_LIB, "library_id": 102, "current_version": "33.5.0",
             "latest_version": "33.5.0", "new_version_released": False},
            {**_LIB, "library_id": 103, "library_status": "Deprecated"},
        ]}
        resp = await test_client.post("/api/v1/recommendations/generate/batch", json=payload)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 3
        assert data["yes_count"] == 2      # lib 101 (mandatory) + 103 (deprecated)
        assert data["sufficient_count"] == 1  # lib 102


class TestCachedResults:
    @pytest.mark.asyncio
    async def test_get_cached_result_after_generate(self, test_client):
        payload = {**_LIB, "library_id": 200}
        await test_client.post("/api/v1/recommendations/generate/200", json=payload)
        resp = await test_client.get("/api/v1/recommendations/200")
        assert resp.status_code == 200
        assert resp.json()["data"]["library_id"] == 200

    @pytest.mark.asyncio
    async def test_get_unknown_library_returns_404(self, test_client):
        resp = await test_client.get("/api/v1/recommendations/99999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_all_returns_list(self, test_client):
        resp = await test_client.get("/api/v1/recommendations")
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)


class TestLLMTest:
    @pytest.mark.asyncio
    async def test_test_llm_returns_disabled_when_not_configured(self, test_client):
        resp = await test_client.post(
            "/api/v1/recommendations/test-llm",
            json={"package": "com.example:lib", "platform": "Android",
                  "current_version": "1.0.0", "latest_version": "2.0.0"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["llm_enabled"] is False
        assert data["success"] is False

"""
Integration tests for scraper-service HTTP endpoints.
All external HTTP calls are mocked.
"""
from __future__ import annotations
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

import httpx
import pytest

from src.models.schemas import ScrapedVersion


def _mock_scraped(package: str, version: str = "2.0.0") -> ScrapedVersion:
    return ScrapedVersion(
        package=package,
        registry="maven",
        latest_version=version,
        scraped_at=datetime.now(timezone.utc),
    )


class TestHealthRouter:
    @pytest.mark.asyncio
    async def test_health_returns_200(self, test_client):
        resp = await test_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "registered_strategies" in data
        assert "maven" in data["registered_strategies"]


class TestRegistriesRouter:
    @pytest.mark.asyncio
    async def test_list_registries_returns_all_mvp(self, test_client):
        resp = await test_client.get("/api/v1/registries")
        assert resp.status_code == 200
        body = resp.json()
        keys = [r["registry_key"] for r in body["data"]]
        assert "maven" in keys
        assert "cocoapods" in keys
        assert "spm" in keys
        assert "github" in keys
        assert "custom" in keys


class TestScrapeRouter:
    @pytest.mark.asyncio
    async def test_scrape_one_returns_version(self, test_client):
        with patch(
            "src.strategies.maven.MavenCentralScraper.fetch",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = _mock_scraped("com.example:lib", "1.2.3")
            resp = await test_client.post(
                "/api/v1/scrape",
                json={"package": "com.example:lib", "registry": "maven"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["latest_version"] == "1.2.3"
        assert body["data"]["registry"] == "maven"

    @pytest.mark.asyncio
    async def test_scrape_unsupported_registry_returns_400(self, test_client):
        resp = await test_client.post(
            "/api/v1/scrape",
            json={"package": "some-package", "registry": "nuget"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_scrape_not_found_returns_404(self, test_client):
        from src.exceptions import PackageNotFoundError
        with patch(
            "src.strategies.maven.MavenCentralScraper.fetch",
            new_callable=AsyncMock,
            side_effect=PackageNotFoundError("not found"),
        ):
            resp = await test_client.post(
                "/api/v1/scrape",
                json={"package": "com.missing:lib", "registry": "maven"},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_scrape_circuit_open_returns_503(self, test_client):
        from src.exceptions import CircuitOpenError
        with patch(
            "src.strategies.maven.MavenCentralScraper.fetch",
            new_callable=AsyncMock,
            side_effect=CircuitOpenError("circuit open"),
        ):
            resp = await test_client.post(
                "/api/v1/scrape",
                json={"package": "com.example:lib", "registry": "maven"},
            )
        assert resp.status_code == 503


class TestBatchScrapeRouter:
    @pytest.mark.asyncio
    async def test_batch_scrape_returns_job_id(self, test_client):
        resp = await test_client.post(
            "/api/v1/scrape/batch",
            json={"libraries": [
                {"package": "com.example:a", "registry": "maven"},
                {"package": "Alamofire", "registry": "cocoapods"},
            ]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "job_id" in body["data"]
        assert body["data"]["total"] == 2

    @pytest.mark.asyncio
    async def test_job_status_returns_404_for_unknown_job(self, test_client):
        resp = await test_client.get("/api/v1/scrape/status/nonexistent-job-id")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_job_status_returns_running_for_valid_job(self, test_client):
        # Create a batch job first
        resp = await test_client.post(
            "/api/v1/scrape/batch",
            json={"libraries": [{"package": "com.example:a", "registry": "maven"}]},
        )
        job_id = resp.json()["data"]["job_id"]

        # Poll status
        status_resp = await test_client.get(f"/api/v1/scrape/status/{job_id}")
        assert status_resp.status_code == 200
        body = status_resp.json()
        assert body["data"]["job_id"] == job_id
        assert body["data"]["total"] == 1

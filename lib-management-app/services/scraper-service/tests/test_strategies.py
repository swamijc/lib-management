"""
Unit tests for ScraperStrategy implementations.
All HTTP calls mocked with httpx.MockTransport.
"""
from __future__ import annotations
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.exceptions import PackageNotFoundError, ParseError
from src.models.schemas import ScrapedVersion
from src.strategies.maven import MavenCentralScraper
from src.strategies.cocoapods import CocoaPodsScraper
from src.strategies.spm import SwiftPackageIndexScraper
from src.strategies.github import GitHubReleasesScraper
from src.strategies.custom_http import CustomHTTPScraper


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_response(status_code: int, body: dict | list | str, is_xml: bool = False) -> httpx.Response:
    if is_xml:
        return httpx.Response(
            status_code=status_code,
            content=body.encode("utf-8") if isinstance(body, str) else str(body).encode("utf-8"),
            headers={"Content-Type": "application/xml"},
            request=httpx.Request("GET", "https://example.com"),
        )
    return httpx.Response(
        status_code=status_code,
        json=body,
        request=httpx.Request("GET", "https://example.com"),
    )


# ── Maven Central ─────────────────────────────────────────────────────────────

class TestMavenCentralScraper:
    @pytest.fixture
    def scraper(self):
        return MavenCentralScraper()

    def test_registry_key(self, scraper):
        assert scraper.registry_key == "maven"

    @pytest.mark.asyncio
    async def test_fetch_returns_version(self, scraper):
        mock_xml = """
        <metadata>
            <groupId>com.example</groupId>
            <artifactId>mylib</artifactId>
            <versioning>
                <latest>1.5.0</latest>
                <release>1.5.0</release>
                <lastUpdated>20250101000000</lastUpdated>
            </versioning>
        </metadata>
        """
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mock_response(200, mock_xml, is_xml=True)
            result = await scraper.fetch("com.example:mylib")

        assert isinstance(result, ScrapedVersion)
        assert result.latest_version == "1.5.0"
        assert result.registry == "maven"
        assert result.package == "com.example:mylib"

    @pytest.mark.asyncio
    async def test_fetch_raises_not_found_for_empty_docs(self, scraper):
        mock_xml = "<metadata><versioning></versioning></metadata>"
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mock_response(200, mock_xml, is_xml=True)
            with pytest.raises(ParseError):
                await scraper.fetch("com.example:missing")

    @pytest.mark.asyncio
    async def test_fetch_raises_parse_error_for_bad_coords(self, scraper):
        with pytest.raises(ParseError):
            await scraper.fetch("no-colon-here")


# ── CocoaPods ─────────────────────────────────────────────────────────────────

class TestCocoaPodsScraper:
    @pytest.fixture
    def scraper(self):
        return CocoaPodsScraper()

    def test_registry_key(self, scraper):
        assert scraper.registry_key == "cocoapods"

    @pytest.mark.asyncio
    async def test_fetch_returns_version(self, scraper):
        mock_body = {
            "versions": [
                {"name": "1.0.0", "created_at": "2024-01-01T00:00:00Z"},
                {"name": "2.0.0", "created_at": "2025-01-01T00:00:00Z"},
            ]
        }
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mock_response(200, mock_body)
            result = await scraper.fetch("Alamofire")

        assert result.latest_version == "2.0.0"
        assert result.registry == "cocoapods"
        assert result.release_date == "2025-01-01"

    @pytest.mark.asyncio
    async def test_fetch_raises_not_found_on_404(self, scraper):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = httpx.Response(
                404, json={}, request=httpx.Request("GET", "https://example.com")
            )
            with pytest.raises(PackageNotFoundError):
                await scraper.fetch("NonExistentPod")


# ── Swift Package Index ───────────────────────────────────────────────────────

class TestSwiftPackageIndexScraper:
    @pytest.fixture
    def scraper(self):
        return SwiftPackageIndexScraper()

    def test_registry_key(self, scraper):
        assert scraper.registry_key == "spm"

    @pytest.mark.asyncio
    async def test_fetch_returns_version(self, scraper):
        mock_body = [
            {"version": "5.12.0", "publishedAt": "2025-03-01T00:00:00Z"},
            {"version": "5.11.0", "publishedAt": "2025-01-01T00:00:00Z"},
        ]
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mock_response(200, mock_body)
            result = await scraper.fetch("Alamofire/Alamofire")

        assert result.latest_version == "5.12.0"
        assert result.registry == "spm"

    @pytest.mark.asyncio
    async def test_fetch_raises_parse_error_for_bad_package(self, scraper):
        with pytest.raises(ParseError):
            await scraper.fetch("NoSlashHere")

    @pytest.mark.asyncio
    async def test_fetch_raises_not_found_on_404(self, scraper):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = httpx.Response(
                404, json={}, request=httpx.Request("GET", "https://example.com")
            )
            with pytest.raises(PackageNotFoundError):
                await scraper.fetch("owner/missing-repo")


# ── GitHub Releases ───────────────────────────────────────────────────────────

class TestGitHubReleasesScraper:
    @pytest.fixture
    def scraper(self):
        return GitHubReleasesScraper()

    def test_registry_key(self, scraper):
        assert scraper.registry_key == "github"

    @pytest.mark.asyncio
    async def test_fetch_strips_v_prefix(self, scraper):
        mock_body = {
            "tag_name": "v4.6.0",
            "published_at": "2025-05-01T00:00:00Z",
            "html_url": "https://github.com/airbnb/lottie-ios/releases/tag/v4.6.0",
            "body": "Release notes here",
        }
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mock_response(200, mock_body)
            result = await scraper.fetch("airbnb/lottie-ios")

        assert result.latest_version == "4.6.0"  # 'v' stripped
        assert result.registry == "github"
        assert result.release_notes == "Release notes here"

    @pytest.mark.asyncio
    async def test_fetch_raises_not_found_on_404(self, scraper):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = httpx.Response(
                404, json={}, request=httpx.Request("GET", "https://example.com")
            )
            with pytest.raises(PackageNotFoundError):
                await scraper.fetch("owner/missing-repo")

    @pytest.mark.asyncio
    async def test_fetch_raises_parse_error_for_bad_package(self, scraper):
        with pytest.raises(ParseError):
            await scraper.fetch("no-slash")


# ── Custom HTTP ───────────────────────────────────────────────────────────────

class TestCustomHTTPScraper:
    @pytest.fixture
    def scraper(self):
        return CustomHTTPScraper()

    def test_registry_key(self, scraper):
        assert scraper.registry_key == "custom"

    @pytest.mark.asyncio
    async def test_fetch_reads_version_field(self, scraper):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mock_response(200, {"version": "3.0.1"})
            result = await scraper.fetch("ACI-ipworks3ds_sdk",
                                         custom_url="https://example.com/sdk/version")

        assert result.latest_version == "3.0.1"
        assert result.registry == "custom"

    @pytest.mark.asyncio
    async def test_fetch_raises_parse_error_without_url(self, scraper):
        with pytest.raises(ParseError):
            await scraper.fetch("SomeSDK")  # no custom_url kwarg

    @pytest.mark.asyncio
    async def test_fetch_raises_parse_error_when_no_version_field(self, scraper):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mock_response(200, {"unrelated_field": "xyz"})
            with pytest.raises(ParseError):
                await scraper.fetch("SomeSDK", custom_url="https://example.com/api")

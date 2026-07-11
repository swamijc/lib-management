"""
Scraper Service — test fixtures.
All HTTP calls are mocked via unittest.mock; no real network calls.
"""
from __future__ import annotations
import os

# Set required env vars BEFORE any src imports
os.environ.setdefault("INTERNAL_SERVICE_KEY", "test-internal-key")
os.environ.setdefault("LOG_LEVEL", "WARNING")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.strategies.base import ScraperFactory
from src.strategies.maven import MavenCentralScraper
from src.strategies.cocoapods import CocoaPodsScraper
from src.strategies.spm import SwiftPackageIndexScraper
from src.strategies.github import GitHubReleasesScraper
from src.strategies.custom_http import CustomHTTPScraper


def _register_all():
    """Register all MVP strategies into ScraperFactory."""
    for s in [
        MavenCentralScraper(),
        CocoaPodsScraper(),
        SwiftPackageIndexScraper(),
        GitHubReleasesScraper(),
        CustomHTTPScraper(),
    ]:
        ScraperFactory.register(s)


@pytest_asyncio.fixture
async def test_client():
    """FastAPI test client with all strategies pre-registered."""
    _register_all()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
    ScraperFactory._registry.clear()


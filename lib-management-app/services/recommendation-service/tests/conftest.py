"""Recommendation Service — test fixtures."""
from __future__ import annotations
import os

os.environ.setdefault("INTERNAL_SERVICE_KEY", "test-internal-key")
os.environ.setdefault("LOG_LEVEL", "WARNING")
# LLM disabled in tests — all tests exercise rule-based path
os.environ.setdefault("LLM_PROVIDER", "")
os.environ.setdefault("LLM_API_KEY", "")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest_asyncio.fixture
async def test_client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

"""Notification Service — test fixtures. All channels mocked; no real SMTP/Teams calls."""
from __future__ import annotations
import os
import sys
from unittest.mock import MagicMock

os.environ.setdefault("INTERNAL_SERVICE_KEY", "test-internal-key")
os.environ.setdefault("LOG_LEVEL", "WARNING")
# Channels disabled — tests mock send_email / send_teams directly
os.environ.setdefault("SMTP_USERNAME", "")
os.environ.setdefault("SMTP_PASSWORD", "")
os.environ.setdefault("TEAMS_WEBHOOK_URL", "")

# Inject aiosmtplib stub so import succeeds without the package
if "aiosmtplib" not in sys.modules:
    sys.modules["aiosmtplib"] = MagicMock()

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from src.main import app


@pytest_asyncio.fixture
async def test_client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

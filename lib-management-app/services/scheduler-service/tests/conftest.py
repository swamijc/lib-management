"""Scheduler Service — test fixtures. All downstream HTTP calls mocked."""
from __future__ import annotations
import os

os.environ.setdefault("INTERNAL_SERVICE_KEY", "test-internal-key")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("SCHEDULE_ENABLED", "false")   # disable APScheduler in tests

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.routers.scheduler import _svc
import src.routers.scheduler as _router_module
import src.services.scheduler_service as _svc_module


@pytest_asyncio.fixture(autouse=True)
async def reset_state():
    """Clear run history and pipeline lock between tests."""
    _svc_module._run_history.clear()
    _svc_module._pipeline_running = False
    yield
    _svc_module._run_history.clear()
    _svc_module._pipeline_running = False


@pytest_asyncio.fixture
async def test_client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

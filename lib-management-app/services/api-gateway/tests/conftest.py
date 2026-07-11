"""API Gateway — test fixtures."""
from __future__ import annotations
import os
from unittest.mock import patch, MagicMock

os.environ.setdefault("INTERNAL_SERVICE_KEY", "test-internal-key")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-testing-only")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Patch user_db so tests don't need real SQLite
from src.auth import user_db as _user_db_module

_MOCK_USERS = {
    "admin": {"id": 1, "username": "admin", "password_hash": _user_db_module.hash_password("adminpass"),
               "role": "admin", "is_active": True},
    "viewer": {"id": 2, "username": "viewer", "password_hash": _user_db_module.hash_password("viewerpass"),
                "role": "viewer", "is_active": True},
}


def _mock_get_user(username: str) -> dict | None:
    return _MOCK_USERS.get(username)


def _mock_authenticate(username: str, password: str) -> dict | None:
    user = _mock_get_user(username)
    if user and _user_db_module.verify_password(password, user["password_hash"]):
        return user
    return None


@pytest.fixture(autouse=True)
def patch_user_db():
    with patch.object(_user_db_module, "get_user", side_effect=_mock_get_user), \
         patch.object(_user_db_module, "authenticate_user", side_effect=_mock_authenticate), \
         patch.object(_user_db_module, "ensure_default_admin", return_value=None):
        yield


from src.main import app


@pytest_asyncio.fixture
async def test_client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest_asyncio.fixture
async def admin_token(test_client) -> str:
    resp = await test_client.post(
        "/auth/token",
        data={"username": "admin", "password": "adminpass"},
    )
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def viewer_token(test_client) -> str:
    resp = await test_client.post(
        "/auth/token",
        data={"username": "viewer", "password": "viewerpass"},
    )
    return resp.json()["access_token"]

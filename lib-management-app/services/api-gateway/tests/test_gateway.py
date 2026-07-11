"""
Tests for api-gateway — auth, JWT, proxy routing (backends mocked).
"""
from __future__ import annotations
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from src.auth.jwt_handler import create_access_token, decode_token


# ── JWT unit tests ────────────────────────────────────────────────────────────

class TestJWT:
    def test_create_and_decode_token(self):
        token = create_access_token(subject="alice", role="admin")
        payload = decode_token(token)
        assert payload["sub"] == "alice"
        assert payload["role"] == "admin"

    def test_expired_token_raises(self):
        from datetime import datetime, timezone, timedelta
        from jose import jwt, JWTError
        from src.config import settings

        past = datetime.now(timezone.utc) - timedelta(hours=1)
        token = jwt.encode(
            {"sub": "alice", "role": "admin", "exp": past},
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(JWTError):
            decode_token(token)

    def test_tampered_token_raises(self):
        from jose import JWTError
        with pytest.raises(JWTError):
            decode_token("invalid.token.here")


# ── Auth router tests ─────────────────────────────────────────────────────────

class TestAuthRouter:
    @pytest.mark.asyncio
    async def test_login_returns_token(self, test_client):
        resp = await test_client.post(
            "/auth/token",
            data={"username": "admin", "password": "adminpass"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["role"] == "admin"
        assert body["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_wrong_password_returns_401(self, test_client):
        resp = await test_client.post(
            "/auth/token",
            data={"username": "admin", "password": "wrong"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_unknown_user_returns_401(self, test_client):
        resp = await test_client.post(
            "/auth/token",
            data={"username": "nobody", "password": "pass"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_with_valid_token(self, test_client, admin_token):
        resp = await test_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["username"] == "admin"
        assert resp.json()["role"] == "admin"

    @pytest.mark.asyncio
    async def test_get_me_without_token_returns_401(self, test_client):
        resp = await test_client.get("/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_viewer_login_and_role(self, test_client, viewer_token):
        resp = await test_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "viewer"


# ── Health router tests ───────────────────────────────────────────────────────

class TestHealthRouter:
    @pytest.mark.asyncio
    async def test_health_no_auth_required(self, test_client):
        resp = await test_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_services_health_mocked(self, test_client):
        healthy = {"service": "svc", "status": "healthy", "status_code": 200}
        with patch("src.routers.health._check_service", new_callable=AsyncMock,
                   return_value=healthy):
            resp = await test_client.get("/health/services")
        assert resp.status_code == 200
        data = resp.json()
        assert "services" in data
        assert len(data["services"]) == 6  # all 6 backend services


# ── Proxy router tests ────────────────────────────────────────────────────────

class TestProxyRouter:
    @pytest.mark.asyncio
    async def test_proxy_requires_auth(self, test_client):
        resp = await test_client.get("/api/v1/libraries")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_proxy_forwards_to_backend(self, test_client, admin_token):
        mock_backend_resp = MagicMock()
        mock_backend_resp.content = b'{"success":true,"data":{"libraries":[]}}'
        mock_backend_resp.status_code = 200
        mock_backend_resp.headers = {"content-type": "application/json"}

        with patch("src.middleware.proxy.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.request = AsyncMock(return_value=mock_backend_resp)
            mock_client_cls.return_value = mock_client

            resp = await test_client.get(
                "/api/v1/libraries",
                headers={"Authorization": f"Bearer {admin_token}"},
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_proxy_unknown_route_returns_404(self, test_client, admin_token):
        with patch("src.middleware.proxy._resolve_backend", return_value=None):
            resp = await test_client.get(
                "/api/v1/unknown-path",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_proxy_backend_unavailable_returns_503(self, test_client, admin_token):
        import httpx as _httpx
        with patch("src.middleware.proxy.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.request = AsyncMock(side_effect=_httpx.ConnectError("refused"))
            mock_client_cls.return_value = mock_client

            resp = await test_client.get(
                "/api/v1/libraries",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503

"""
Base async HTTPX client used by all services for inter-service HTTP calls.
Attaches the internal service key header automatically.
"""
from __future__ import annotations
import httpx
from typing import Any


class InternalHttpClient:
    """
    Thin wrapper around httpx.AsyncClient for internal service-to-service calls.
    Attaches X-Internal-Service-Key and Accept: application/json automatically.
    """

    def __init__(self, base_url: str, internal_key: str, timeout: float = 30.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "X-Internal-Service-Key": internal_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(timeout),
        )

    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self._client.get(path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self._client.post(path, **kwargs)

    async def put(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self._client.put(path, **kwargs)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "InternalHttpClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

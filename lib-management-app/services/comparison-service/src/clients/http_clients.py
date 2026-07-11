"""
Comparison Service — HTTP clients for library-data-service and scraper-service.
"""
from __future__ import annotations

import httpx
import structlog

from ..config import settings

logger = structlog.get_logger(__name__)

_HEADERS = {"X-Internal-Service-Key": settings.internal_service_key}


async def fetch_all_libraries(skip: int = 0, limit: int = 500) -> list[dict]:
    """Fetch library records from library-data-service."""
    url = f"{settings.library_data_service_url}/api/v1/libraries"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            url,
            params={"skip": skip, "limit": limit},
            headers=_HEADERS,
        )
        resp.raise_for_status()
    body = resp.json()
    return body.get("data", {}).get("libraries", [])


async def fetch_library(library_id: int) -> dict:
    """Fetch a single library record."""
    url = f"{settings.library_data_service_url}/api/v1/libraries/{library_id}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, headers=_HEADERS)
        resp.raise_for_status()
    return resp.json().get("data", {})


async def scrape_library(package: str, registry: str, custom_url: str | None = None) -> dict:
    """Call scraper-service for the latest version of a library."""
    url = f"{settings.scraper_service_url}/api/v1/scrape"
    payload: dict = {"package": package, "registry": registry}
    if custom_url:
        payload["custom_url"] = custom_url
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload, headers=_HEADERS)
        resp.raise_for_status()
    return resp.json().get("data", {})

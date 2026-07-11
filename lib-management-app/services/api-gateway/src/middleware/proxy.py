"""
API Gateway — generic reverse proxy.

Forwards authenticated requests to the appropriate backend service,
injecting the internal service key header.
"""
from __future__ import annotations

import httpx
import structlog
from fastapi import Request, Response

from ..config import settings

logger = structlog.get_logger(__name__)

_INTERNAL_HEADERS = {"X-Internal-Service-Key": settings.internal_service_key}
_PROXY_TIMEOUT = 60.0

# Route table: path prefix → base URL
_ROUTE_MAP: list[tuple[str, str]] = [
    ("/api/v1/libraries",          settings.library_data_service_url),
    ("/api/v1/version-history",    settings.library_data_service_url),
    ("/api/v1/pipeline-runs",      settings.library_data_service_url),
    ("/api/v1/settings",           settings.library_data_service_url),
    ("/api/v1/audit-log",          settings.library_data_service_url),
    ("/api/v1/lifecycle",          settings.library_data_service_url),
    ("/api/v1/llm",                settings.library_data_service_url),
    ("/api/v1/cve",                settings.library_data_service_url),
    ("/api/v1/teams",              settings.library_data_service_url),
    ("/api/v1/sla",                settings.library_data_service_url),
    ("/api/v1/scrape",             settings.scraper_service_url),
    ("/api/v1/registries",         settings.scraper_service_url),
    ("/api/v1/compare",            settings.comparison_service_url),
    ("/api/v1/comparisons",        settings.comparison_service_url),
    # Recommendation generation/testing stays on recommendation-service.
    ("/api/v1/recommendations/generate", settings.recommendation_service_url),
    ("/api/v1/recommendations/test-llm", settings.recommendation_service_url),
    ("/api/v1/recommendations/chat", settings.recommendation_service_url),
    # Recommendation reads come from persisted DB records via library-data-service.
    ("/api/v1/recommendations",    settings.library_data_service_url),
    ("/api/v1/notify",             settings.notification_service_url),
    ("/api/v1/notifications",      settings.notification_service_url),
    ("/api/v1/schedule",           settings.scheduler_service_url),
    ("/api/v1/run",                settings.scheduler_service_url),
    ("/api/v1/runs",               settings.scheduler_service_url),
]


def _resolve_backend(path: str) -> str | None:
    for prefix, base_url in _ROUTE_MAP:
        if path.startswith(prefix):
            return base_url
    return None


async def proxy_request(request: Request) -> Response:
    """
    Forward the incoming request to the resolved backend service.
    Strips the gateway's own Authorization header; injects X-Internal-Service-Key.
    """
    path = request.url.path
    backend = _resolve_backend(path)
    if backend is None:
        return Response(content='{"detail":"Route not found"}',
                        status_code=404, media_type="application/json")

    target_url = f"{backend}{path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    # Forward headers except Authorization (auth already validated by gateway)
    forward_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "authorization", "content-length")
    }
    forward_headers.update(_INTERNAL_HEADERS)

    body = await request.body()

    try:
        async with httpx.AsyncClient(timeout=_PROXY_TIMEOUT) as client:
            resp = await client.request(
                method=request.method,
                url=target_url,
                headers=forward_headers,
                content=body,
            )
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=resp.headers.get("content-type", "application/json"),
        )
    except httpx.ConnectError:
        logger.error("proxy_connect_error", backend=backend, path=path)
        return Response(
            content=f'{{"detail":"Backend service unavailable: {backend}"}}',
            status_code=503,
            media_type="application/json",
        )
    except Exception as exc:
        logger.error("proxy_error", backend=backend, path=path, error=str(exc))
        return Response(
            content='{"detail":"Gateway proxy error"}',
            status_code=502,
            media_type="application/json",
        )

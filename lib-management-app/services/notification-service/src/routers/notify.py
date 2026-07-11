"""
Notification Service — routers.

Endpoints:
  POST /api/v1/notify/email   — send email only
  POST /api/v1/notify/teams   — send Teams message only
  POST /api/v1/notify/both    — send both channels
  GET  /api/v1/notifications  — list in-memory send log (last N results)
"""
from __future__ import annotations
from collections import deque

from fastapi import APIRouter

from ..config import settings
from ..models.schemas import NotifyRequest, NotifyResult
from ..services.notification_service import NotificationService
from shared.models.base_schemas import ApiResponse, ResponseMeta

router = APIRouter(prefix="/api/v1", tags=["notifications"])
_svc = NotificationService()

# Rolling in-memory log of last 200 results
_log: deque[NotifyResult] = deque(maxlen=200)


def _meta() -> ResponseMeta:
    return ResponseMeta(service=settings.service_name, version=settings.service_version)


@router.post("/notify/email", response_model=ApiResponse[NotifyResult])
async def notify_email(req: NotifyRequest) -> ApiResponse[NotifyResult]:
    """Send HTML email notification to configured recipients."""
    result = await _svc.notify_email(req)
    _log.append(result)
    return ApiResponse.ok(data=result, meta=_meta())


@router.post("/notify/teams", response_model=ApiResponse[NotifyResult])
async def notify_teams(req: NotifyRequest) -> ApiResponse[NotifyResult]:
    """Post Adaptive Card to Microsoft Teams webhook."""
    result = await _svc.notify_teams(req)
    _log.append(result)
    return ApiResponse.ok(data=result, meta=_meta())


@router.post("/notify/both", response_model=ApiResponse[NotifyResult])
async def notify_both(req: NotifyRequest) -> ApiResponse[NotifyResult]:
    """Send both email and Teams notifications."""
    result = await _svc.notify_both(req)
    _log.append(result)
    return ApiResponse.ok(data=result, meta=_meta())


@router.get("/notifications", response_model=ApiResponse[list[NotifyResult]])
async def list_notifications() -> ApiResponse[list[NotifyResult]]:
    """Return recent notification results (in-memory, resets on restart)."""
    return ApiResponse.ok(data=list(_log), meta=_meta())

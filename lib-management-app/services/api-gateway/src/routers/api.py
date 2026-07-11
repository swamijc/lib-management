"""API Gateway — API proxy router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from ..auth.dependencies import get_current_user
from ..middleware.proxy import proxy_request

router = APIRouter(dependencies=[Depends(get_current_user)])

# Write methods that require admin role
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Paths that any authenticated user may write (lifecycle initiation by developers)
_VIEWER_WRITE_ALLOWED_PREFIXES = (
    "/api/v1/lifecycle",  # developers can acknowledge/schedule upgrades
)


@router.api_route(
    "/api/v1/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy(
    request: Request, path: str, user: dict = Depends(get_current_user)
) -> Response:
    """Proxy all /api/v1/* requests to backend services (JWT required).
    Write operations (POST/PUT/PATCH/DELETE) require admin role,
    except for lifecycle endpoints which viewers/developers can also use.
    """
    if request.method in _WRITE_METHODS and user.get("role") != "admin":
        req_path = request.url.path
        if not any(req_path.startswith(p) for p in _VIEWER_WRITE_ALLOWED_PREFIXES):
            return JSONResponse(
                status_code=403,
                content={"detail": "Admin access required for write operations"},
            )
    return await proxy_request(request)

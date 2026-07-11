"""Router: /api/v1/libraries"""
from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..exceptions import LibraryNotFoundError
from ..models.schemas import (
    LibraryCreate,
    LibraryFilter,
    LibraryListResponse,
    LibraryResponse,
    LibraryUpdateRequest,
    SetCurrentVersionRequest,
    SetCurrentVersionResponse,
)
from ..services.library_service import LibraryService
from shared.models.base_schemas import ApiResponse, ResponseMeta

router = APIRouter(prefix="/api/v1/libraries", tags=["libraries"])


def _meta() -> ResponseMeta:
    return ResponseMeta(service=settings.service_name, version=settings.service_version)


@router.get("", response_model=ApiResponse[LibraryListResponse])
async def list_libraries(
    platform: str | None = Query(None),
    status: str | None = Query(None),
    update_needed: str | None = Query(None),
    ecosystem: str | None = Query(None),
    alert_priority: str | None = Query(None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[LibraryListResponse]:
    svc = LibraryService(db)
    filters = LibraryFilter(
        platform=platform, status=status, update_needed=update_needed,
        ecosystem=ecosystem, alert_priority=alert_priority, skip=skip, limit=limit,
    )
    items, total = await svc.list_libraries(filters)
    return ApiResponse.ok(
        data=LibraryListResponse(
            libraries=[LibraryResponse.model_validate(lib) for lib in items],
            total=total, skip=skip, limit=limit,
        ),
        meta=_meta(),
    )


@router.get("/critical", response_model=ApiResponse[list[LibraryResponse]])
async def get_critical_libraries(
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[LibraryResponse]]:
    """Returns all libraries with alert_priority=Critical (B7)."""
    svc = LibraryService(db)
    items = await svc.get_critical()
    return ApiResponse.ok(
        data=[LibraryResponse.model_validate(lib) for lib in items],
        meta=_meta(),
    )


@router.get("/platform/{platform}", response_model=ApiResponse[list[LibraryResponse]])
async def get_by_platform(
    platform: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[LibraryResponse]]:
    svc = LibraryService(db)
    items = await svc.get_by_platform(platform)
    return ApiResponse.ok(
        data=[LibraryResponse.model_validate(lib) for lib in items],
        meta=_meta(),
    )


@router.get("/{library_id}", response_model=ApiResponse[LibraryResponse])
async def get_library(
    library_id: int,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[LibraryResponse]:
    svc = LibraryService(db)
    lib = await svc.get_library(library_id)  # raises LibraryNotFoundError → 404 handler
    return ApiResponse.ok(data=LibraryResponse.model_validate(lib), meta=_meta())


@router.post("", response_model=ApiResponse[LibraryResponse], status_code=201)
async def create_library(
    request: LibraryCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[LibraryResponse]:
    svc = LibraryService(db)
    lib = await svc.create_library(request)
    return ApiResponse.ok(data=LibraryResponse.model_validate(lib), meta=_meta())


@router.put("/{library_id}", response_model=ApiResponse[LibraryResponse])
async def update_library(
    library_id: int,
    request: LibraryUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[LibraryResponse]:
    svc = LibraryService(db)
    lib = await svc.update_library(library_id, request)  # raises LibraryNotFoundError → 404 handler
    return ApiResponse.ok(data=LibraryResponse.model_validate(lib), meta=_meta())


@router.post("/{library_id}/set-current-version", response_model=ApiResponse[SetCurrentVersionResponse])
async def set_current_version(
    library_id: int,
    request: SetCurrentVersionRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[SetCurrentVersionResponse]:
    """Set a selected historical version as the library's current active version."""
    svc = LibraryService(db)
    lib = await svc.set_current_active_version(library_id, request)
    return ApiResponse.ok(
        data=SetCurrentVersionResponse(
            library_id=lib.id,
            current_version=lib.current_version or "",
            status=lib.status,
        ),
        meta=_meta(),
    )


@router.delete("/{library_id}", response_model=ApiResponse[dict])
async def delete_library(
    library_id: int,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    svc = LibraryService(db)
    await svc.delete_library(library_id)  # raises LibraryNotFoundError → 404 handler
    return ApiResponse.ok(data={"deleted": library_id}, meta=_meta())

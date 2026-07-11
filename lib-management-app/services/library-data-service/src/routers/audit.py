"""Router: /api/v1/audit-log — immutable change history."""
from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models.orm import Library, LibraryUpdateLog
from ..models.schemas import AuditLogResponse
from shared.models.base_schemas import ApiResponse, ResponseMeta

router = APIRouter(prefix="/api/v1/audit-log", tags=["audit"])


def _meta() -> ResponseMeta:
    return ResponseMeta(service=settings.service_name, version=settings.service_version)


@router.get("", response_model=ApiResponse[list[AuditLogResponse]])
async def list_audit_log(
    library_id: int | None = Query(None),
    updated_by: str | None = Query(None),
    field_changed: str | None = Query(None),
    date_from: str | None = Query(None, description="ISO date YYYY-MM-DD"),
    date_to: str | None = Query(None, description="ISO date YYYY-MM-DD"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[AuditLogResponse]]:
    """
    Return audit log entries with optional filters.
    Joined to libraries table to include package + sdk_name.
    """
    stmt = (
        select(LibraryUpdateLog, Library.package, Library.sdk_name)
        .join(Library, Library.id == LibraryUpdateLog.library_id, isouter=True)
        .order_by(LibraryUpdateLog.updated_at.desc())
    )

    if library_id is not None:
        stmt = stmt.where(LibraryUpdateLog.library_id == library_id)
    if updated_by:
        stmt = stmt.where(LibraryUpdateLog.updated_by == updated_by)
    if field_changed:
        stmt = stmt.where(LibraryUpdateLog.field_changed == field_changed)
    if date_from:
        stmt = stmt.where(LibraryUpdateLog.updated_at >= date_from)
    if date_to:
        stmt = stmt.where(LibraryUpdateLog.updated_at <= date_to + "T23:59:59")

    stmt = stmt.offset(skip).limit(limit)
    rows = (await db.execute(stmt)).all()

    data = [
        AuditLogResponse(
            id=row.LibraryUpdateLog.id,
            library_id=row.LibraryUpdateLog.library_id,
            updated_by=row.LibraryUpdateLog.updated_by,
            update_type=row.LibraryUpdateLog.update_type,
            field_changed=row.LibraryUpdateLog.field_changed,
            old_value=row.LibraryUpdateLog.old_value,
            new_value=row.LibraryUpdateLog.new_value,
            reason=row.LibraryUpdateLog.reason,
            updated_at=row.LibraryUpdateLog.updated_at,
            package=row.package,
            sdk_name=row.sdk_name,
        )
        for row in rows
    ]
    return ApiResponse.ok(data=data, meta=_meta())

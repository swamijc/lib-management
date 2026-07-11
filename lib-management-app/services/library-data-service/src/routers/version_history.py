"""Router: /api/v1/version-history"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models.schemas import VersionHistoryCreate, VersionHistoryResponse
from ..repositories.library_repo import VersionHistoryRepository
from shared.models.base_schemas import ApiResponse, ResponseMeta

router = APIRouter(prefix="/api/v1/version-history", tags=["version-history"])


def _meta() -> ResponseMeta:
    return ResponseMeta(service=settings.service_name, version=settings.service_version)


@router.get("/{library_id}", response_model=ApiResponse[list[VersionHistoryResponse]])
async def get_version_history(
    library_id: int,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[VersionHistoryResponse]]:
    repo = VersionHistoryRepository(db)
    items = await repo.get_by_library(library_id)
    return ApiResponse.ok(
        data=[VersionHistoryResponse.model_validate(i) for i in items],
        meta=_meta(),
    )


@router.post("", response_model=ApiResponse[VersionHistoryResponse])
async def create_version_history(
    data: VersionHistoryCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[VersionHistoryResponse]:
    repo = VersionHistoryRepository(db)
    entry = await repo.create(
        library_id=data.library_id,
        version_number=data.version_number,
        record_type=data.record_type,
        source=data.source,
        notes=data.notes,
    )
    return ApiResponse.ok(data=VersionHistoryResponse.model_validate(entry), meta=_meta())

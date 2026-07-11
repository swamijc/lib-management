"""Router: /api/v1/recommendations"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models.schemas import RecommendationCreate, RecommendationResponse
from ..repositories.other_repos import RecommendationRepository
from shared.models.base_schemas import ApiResponse, ResponseMeta

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])


def _meta() -> ResponseMeta:
    return ResponseMeta(service=settings.service_name, version=settings.service_version)


@router.get("", response_model=ApiResponse[list[RecommendationResponse]])
async def get_all(db: AsyncSession = Depends(get_db)) -> ApiResponse[list[RecommendationResponse]]:
    repo = RecommendationRepository(db)
    items = await repo.get_all()
    return ApiResponse.ok(data=[RecommendationResponse.from_orm_with_json(i) for i in items], meta=_meta())


@router.get("/{library_id}", response_model=ApiResponse[RecommendationResponse | None])
async def get_for_library(library_id: int, db: AsyncSession = Depends(get_db)):
    repo = RecommendationRepository(db)
    item = await repo.get_by_library(library_id)
    return ApiResponse.ok(
        data=RecommendationResponse.from_orm_with_json(item) if item else None,
        meta=_meta(),
    )


@router.post("", response_model=ApiResponse[RecommendationResponse])
async def create(data: RecommendationCreate, db: AsyncSession = Depends(get_db)):
    repo = RecommendationRepository(db)
    rec = await repo.create(data)
    return ApiResponse.ok(data=RecommendationResponse.from_orm_with_json(rec), meta=_meta())

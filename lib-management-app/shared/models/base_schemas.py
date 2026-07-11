"""
Standard JSON response envelope used by every service.
All API responses wrap data in this structure for consistency.
"""
from typing import Any, Generic, TypeVar
from pydantic import BaseModel, Field
from datetime import datetime, timezone

T = TypeVar("T")


class ResponseMeta(BaseModel):
    service: str
    version: str
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ErrorDetail(BaseModel):
    code: str
    message: str
    detail: Any | None = None


class ApiResponse(BaseModel, Generic[T]):
    """Standard envelope for all API responses."""
    success: bool
    data: T | None = None
    error: ErrorDetail | None = None
    meta: ResponseMeta

    @classmethod
    def ok(cls, data: T, meta: ResponseMeta) -> "ApiResponse[T]":
        return cls(success=True, data=data, error=None, meta=meta)

    @classmethod
    def fail(cls, code: str, message: str, meta: ResponseMeta, detail: Any = None) -> "ApiResponse[None]":
        return cls(
            success=False,
            data=None,
            error=ErrorDetail(code=code, message=message, detail=detail),
            meta=meta,
        )


class PaginatedData(BaseModel, Generic[T]):
    """Wrapper for paginated list responses."""
    items: list[T]
    total: int
    skip: int = 0
    limit: int = 100

"""
Library Service — business logic layer.
Orchestrates repository calls; keeps routers thin.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone

try:
    from packaging.version import Version as _PkgVersion, InvalidVersion as _InvalidVersion
    _PACKAGING_AVAILABLE = True
except ImportError:
    _PACKAGING_AVAILABLE = False


def _derive_update_needed(current: str | None, latest: str | None) -> str:
    """
    Derive update_needed priority by comparing current vs latest version.

    Returns one of: "none" | "optional" | "recommended" | "mandatory"

    Rules:
      current == latest          → none  (up to date)
      current > latest           → none  (pinned ahead, treat as up to date)
      major(latest) > major(cur) → mandatory
      minor(latest) > minor(cur) → recommended
      patch(latest) > patch(cur) → optional
    """
    if not current or not latest:
        return "none"
    if current.strip() == latest.strip():
        return "none"

    if _PACKAGING_AVAILABLE:
        try:
            cur_v = _PkgVersion(current.lstrip("v"))
            lat_v = _PkgVersion(latest.lstrip("v"))
        except _InvalidVersion:
            return "recommended"  # can't parse → safe default

        if cur_v >= lat_v:
            return "none"
        if lat_v.major > cur_v.major:
            return "mandatory"
        if lat_v.minor > cur_v.minor:
            return "recommended"
        return "optional"

    # Fallback: simple numeric tuple comparison when packaging is unavailable
    def _to_tuple(v: str) -> tuple[int, ...]:
        parts = v.lstrip("v").split(".")
        result = []
        for p in parts[:3]:
            try:
                result.append(int(p.split("-")[0].split("+")[0]))
            except ValueError:
                result.append(0)
        while len(result) < 3:
            result.append(0)
        return tuple(result)

    try:
        c = _to_tuple(current)
        l = _to_tuple(latest)
        if c >= l:
            return "none"
        if l[0] > c[0]:
            return "mandatory"
        if l[1] > c[1]:
            return "recommended"
        return "optional"
    except Exception:
        return "recommended"

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..exceptions import LibraryNotFoundError, ValidationError, VersionNotFoundError
from ..models.orm import Library, LibraryUpdateLog, LibraryVersion
from ..models.schemas import (
    LibraryCreate,
    LibraryFilter,
    LibraryUpdate,
    LibraryUpdateRequest,
    SetCurrentVersionRequest,
)
from ..repositories.library_repo import LibraryRepository, VersionHistoryRepository


class LibraryService:
    def __init__(self, session: AsyncSession) -> None:
        self._lib_repo = LibraryRepository(session)
        self._ver_repo = VersionHistoryRepository(session)
        self._session = session

    async def list_libraries(
        self, filters: LibraryFilter
    ) -> tuple[list[Library], int]:
        return await self._lib_repo.get_all(filters)

    async def get_library(self, library_id: int) -> Library:
        lib = await self._lib_repo.get_by_id(library_id)
        if lib is None:
            raise LibraryNotFoundError(library_id)
        return lib

    async def get_by_platform(self, platform: str) -> list[Library]:
        return await self._lib_repo.get_by_platform(platform)

    async def get_critical(self) -> list[Library]:
        return await self._lib_repo.get_critical_libraries()

    async def create_library(self, data: LibraryCreate) -> Library:
        return await self._lib_repo.create(data)

    async def delete_library(self, library_id: int) -> bool:
        lib = await self._lib_repo.get_by_id(library_id)
        if lib is None:
            raise LibraryNotFoundError(library_id)
        return await self._lib_repo.delete(library_id)

    async def update_library(
        self, library_id: int, request: LibraryUpdateRequest
    ) -> Library:
        """
        Updates a library and writes an audit log entry.
        Raises LibraryNotFoundError if not found.
        """
        lib = await self._lib_repo.get_by_id(library_id)
        if lib is None:
            raise LibraryNotFoundError(library_id)

        # Build update payload (exclude audit fields)
        update_data = LibraryUpdate(**request.model_dump(
            exclude={"updated_by", "reason"}, exclude_none=True
        ))

        # Determine changed fields for audit log
        changed_fields = []
        for field, new_val in update_data.model_dump(exclude_none=True).items():
            old_val = getattr(lib, field, None)
            if str(old_val) != str(new_val):
                changed_fields.append((field, str(old_val), str(new_val)))

        updated_lib = await self._lib_repo.update(library_id, update_data)

        # Write one audit log entry per changed field
        for field, old_val, new_val in changed_fields:
            log_entry = LibraryUpdateLog(
                library_id=library_id,
                updated_by=request.updated_by,
                update_type="manual",
                field_changed=field,
                old_value=old_val,
                new_value=new_val,
                reason=request.reason,
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            self._session.add(log_entry)

        await self._session.flush()
        return updated_lib  # type: ignore[return-value]

    async def system_update_library(
        self,
        library_id: int,
        data: LibraryUpdate,
        updated_by: str = "scheduler",
        reason: str | None = None,
    ) -> Library:
        """
        System-driven update (scraper result, comparison result).
        Also writes audit log; update_type='scheduler' or 'scraper'.
        """
        lib = await self._lib_repo.get_by_id(library_id)
        if lib is None:
            raise LibraryNotFoundError(library_id)

        update_fields = data.model_dump(exclude_none=True)
        for field, new_val in update_fields.items():
            old_val = getattr(lib, field, None)
            if str(old_val) != str(new_val):
                log_entry = LibraryUpdateLog(
                    library_id=library_id,
                    updated_by=updated_by,
                    update_type="scheduler",
                    field_changed=field,
                    old_value=str(old_val),
                    new_value=str(new_val),
                    reason=reason,
                    updated_at=datetime.now(timezone.utc).isoformat(),
                )
                self._session.add(log_entry)

        updated = await self._lib_repo.update(library_id, data)
        await self._session.flush()
        return updated  # type: ignore[return-value]

    async def set_current_active_version(
        self,
        library_id: int,
        request: SetCurrentVersionRequest,
    ) -> Library:
        """
        Set the selected historical version as the library's current active version.

        Behavior:
        - Verifies library exists.
        - Verifies requested version exists in `library_versions` for the library.
        - Updates `library_versions.is_current` flags.
        - Updates `libraries.current_version` and enforces `libraries.status='Active'`.
        - Writes audit log entries for changed fields.
        """
        lib = await self._lib_repo.get_by_id(library_id)
        if lib is None:
            raise LibraryNotFoundError(library_id)

        normalized_version = request.version.strip()
        if not normalized_version:
            raise ValidationError("Version must be a non-empty string")
        if normalized_version != request.version:
            raise ValidationError("Version must not include leading or trailing whitespace")

        selected = (await self._session.execute(
            select(LibraryVersion).where(
                LibraryVersion.library_id == library_id,
                LibraryVersion.version == normalized_version,
            )
        )).scalar_one_or_none()
        if selected is None:
            raise VersionNotFoundError(library_id=library_id, version=normalized_version)

        # Reset current flags for this library, then set selected row as current.
        rows = (await self._session.execute(
            select(LibraryVersion).where(LibraryVersion.library_id == library_id)
        )).scalars().all()
        for row in rows:
            row.is_current = (row.version == normalized_version)

        changed_fields: list[tuple[str, str | None, str | None]] = []
        if str(lib.current_version or "") != normalized_version:
            changed_fields.append(("current_version", lib.current_version, normalized_version))
            lib.current_version = normalized_version
        # NOTE: lib.status and update_needed are intentionally NOT changed here.
        # Status only changes via the lifecycle Set Active flow (set-active endpoint).
        # Priority only changes when lifecycle reaches Completed via set-active.

        lib.updated_at = datetime.now(timezone.utc).isoformat()

        for field, old_val, new_val in changed_fields:
            self._session.add(LibraryUpdateLog(
                library_id=library_id,
                updated_by=request.updated_by,
                update_type="manual",
                field_changed=field,
                old_value=str(old_val) if old_val is not None else None,
                new_value=str(new_val) if new_val is not None else None,
                reason=request.reason,
                updated_at=datetime.now(timezone.utc).isoformat(),
            ))

        await self._session.flush()
        await self._session.refresh(lib)
        return lib

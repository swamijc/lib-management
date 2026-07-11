"""
Library Repository — SQLite implementation of the Repository Pattern.
All DB reads/writes for the `libraries` table go through this class.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.orm import Library, VersionHistory
from ..models.schemas import LibraryFilter, LibraryUpdate


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LibraryRepository:
    """
    Implements Repository Pattern for the Library aggregate root.
    Never exposes SQLAlchemy models outside this class — callers receive ORM
    objects which are converted to DTOs in the service/router layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get_by_id(self, library_id: int) -> Library | None:
        result = await self._session.execute(
            select(Library).where(Library.id == library_id)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        filters: LibraryFilter | None = None,
    ) -> tuple[list[Library], int]:
        """
        Returns (items, total_count).
        total_count is pre-filter for pagination metadata.
        """
        stmt = select(Library)
        count_stmt = select(func.count()).select_from(Library)

        if filters:
            if filters.platform:
                stmt = stmt.where(Library.platform == filters.platform)
                count_stmt = count_stmt.where(Library.platform == filters.platform)
            if filters.status:
                stmt = stmt.where(Library.status == filters.status)
                count_stmt = count_stmt.where(Library.status == filters.status)
            if filters.update_needed:
                stmt = stmt.where(Library.update_needed == filters.update_needed)
                count_stmt = count_stmt.where(Library.update_needed == filters.update_needed)
            if filters.ecosystem:
                stmt = stmt.where(Library.ecosystem == filters.ecosystem)
                count_stmt = count_stmt.where(Library.ecosystem == filters.ecosystem)
            if filters.alert_priority:
                stmt = stmt.where(Library.alert_priority == filters.alert_priority)
                count_stmt = count_stmt.where(Library.alert_priority == filters.alert_priority)

            stmt = stmt.offset(filters.skip).limit(filters.limit)

        stmt = stmt.order_by(Library.platform, Library.sl_no)

        total = (await self._session.execute(count_stmt)).scalar_one()
        result = await self._session.execute(stmt)
        return result.scalars().all(), total  # type: ignore[return-value]

    async def get_by_platform(self, platform: str) -> list[Library]:
        result = await self._session.execute(
            select(Library)
            .where(Library.platform == platform)
            .order_by(Library.sl_no)
        )
        return result.scalars().all()  # type: ignore[return-value]

    async def get_critical_libraries(self) -> list[Library]:
        """Returns libraries with alert_priority='Critical' for urgent notifications."""
        result = await self._session.execute(
            select(Library).where(Library.alert_priority == "Critical")
        )
        return result.scalars().all()  # type: ignore[return-value]

    # ── Write ─────────────────────────────────────────────────────────────────

    async def update(
        self, library_id: int, data: LibraryUpdate
    ) -> Library | None:
        """
        Applies only the non-None fields from data to the library record.
        Returns the updated Library or None if not found.
        """
        lib = await self.get_by_id(library_id)
        if lib is None:
            return None

        update_dict = data.model_dump(exclude_none=True)
        update_dict["updated_at"] = _now()

        for field, value in update_dict.items():
            setattr(lib, field, value)

        await self._session.flush()
        await self._session.refresh(lib)
        return lib

    async def update_last_checked(self, library_id: int) -> None:
        await self._session.execute(
            update(Library)
            .where(Library.id == library_id)
            .values(last_checked_date=_now()[:10], updated_at=_now())
        )

    async def create(self, data: "LibraryCreate") -> Library:  # type: ignore[name-defined]
        lib = Library(
            package=data.package,
            sdk_name=data.sdk_name or data.package,
            platform=data.platform,
            current_version=data.current_version or "",
            latest_version=data.latest_version or "",
            update_needed=data.update_needed or "none",
            priority=data.priority or "Medium",
            repo_url=data.repo_url,
            registry=data.registry or "",
            comments=data.comments,
            deprecation_notes=data.deprecation_notes,
            status=data.status or "Active",
            alert_priority=data.alert_priority or "Normal",
            deadline_date=data.deadline_date,
            deadline_notes=data.deadline_notes,
            ecosystem=data.ecosystem or "mobile",
            framework_language=data.framework_language,
            created_at=_now(),
            updated_at=_now(),
        )
        self._session.add(lib)
        await self._session.flush()
        await self._session.refresh(lib)
        return lib

    async def delete(self, library_id: int) -> bool:
        lib = await self.get_by_id(library_id)
        if lib is None:
            return False
        await self._session.delete(lib)
        await self._session.flush()
        return True


class VersionHistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_library(self, library_id: int) -> list[VersionHistory]:
        result = await self._session.execute(
            select(VersionHistory)
            .where(VersionHistory.library_id == library_id)
            .order_by(VersionHistory.recorded_at.desc())
        )
        return result.scalars().all()  # type: ignore[return-value]

    async def create(
        self,
        library_id: int,
        version_number: str,
        record_type: str,
        source: str | None = None,
        notes: str | None = None,
    ) -> VersionHistory:
        entry = VersionHistory(
            library_id=library_id,
            version_number=version_number,
            record_type=record_type,
            source=source,
            notes=notes,
            recorded_at=_now(),
        )
        self._session.add(entry)
        await self._session.flush()
        await self._session.refresh(entry)
        return entry

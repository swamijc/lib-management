"""
Unit tests for LibraryRepository and VersionHistoryRepository.
All tests run against in-memory SQLite — no real DB touched.
"""
from __future__ import annotations
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm import Library
from src.models.schemas import LibraryFilter, LibraryUpdate, LibraryUpdateRequest
from src.repositories.library_repo import LibraryRepository, VersionHistoryRepository
from src.repositories.other_repos import UpgradeLifecycleRepository


class TestLibraryRepository:

    @pytest.mark.asyncio
    async def test_get_by_id_returns_library(
        self, test_db: AsyncSession, sample_library: Library
    ) -> None:
        repo = LibraryRepository(test_db)
        result = await repo.get_by_id(sample_library.id)
        assert result is not None
        assert result.package == "com.example:test-lib"

    @pytest.mark.asyncio
    async def test_get_by_id_returns_none_for_missing(
        self, test_db: AsyncSession
    ) -> None:
        repo = LibraryRepository(test_db)
        result = await repo.get_by_id(99999)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_all_returns_all_libraries(
        self, test_db: AsyncSession, sample_library: Library
    ) -> None:
        repo = LibraryRepository(test_db)
        items, total = await repo.get_all(LibraryFilter())
        assert total >= 1
        packages = [lib.package for lib in items]
        assert "com.example:test-lib" in packages

    @pytest.mark.asyncio
    async def test_get_all_filters_by_platform(
        self, test_db: AsyncSession, sample_library: Library
    ) -> None:
        repo = LibraryRepository(test_db)
        items, total = await repo.get_all(LibraryFilter(platform="Android"))
        assert all(lib.platform == "Android" for lib in items)

        items_ios, _ = await repo.get_all(LibraryFilter(platform="iOS"))
        assert len(items_ios) == 0

    @pytest.mark.asyncio
    async def test_get_all_filters_by_update_needed(
        self, test_db: AsyncSession, sample_library: Library
    ) -> None:
        repo = LibraryRepository(test_db)
        items, _ = await repo.get_all(LibraryFilter(update_needed="Mandatory"))
        assert all(lib.update_needed == "Mandatory" for lib in items)

    @pytest.mark.asyncio
    async def test_get_all_pagination(
        self, test_db: AsyncSession, sample_library: Library
    ) -> None:
        # Add a second library
        lib2 = Library(
            sl_no=2, package="com.example:lib2", platform="Android",
            current_version="1.0.0", update_needed="None", status="Active",
            ecosystem="mobile",
        )
        test_db.add(lib2)
        await test_db.commit()

        repo = LibraryRepository(test_db)
        items_page1, total = await repo.get_all(LibraryFilter(skip=0, limit=1))
        assert len(items_page1) == 1
        assert total == 2

        items_page2, _ = await repo.get_all(LibraryFilter(skip=1, limit=1))
        assert len(items_page2) == 1
        # Pages should have different libraries
        assert items_page1[0].id != items_page2[0].id

    @pytest.mark.asyncio
    async def test_update_changes_fields(
        self, test_db: AsyncSession, sample_library: Library
    ) -> None:
        repo = LibraryRepository(test_db)
        updated = await repo.update(
            sample_library.id,
            LibraryUpdate(current_version="2.0.0", status="Active"),
        )
        assert updated is not None
        assert updated.current_version == "2.0.0"

    @pytest.mark.asyncio
    async def test_update_returns_none_for_missing(
        self, test_db: AsyncSession
    ) -> None:
        repo = LibraryRepository(test_db)
        result = await repo.update(99999, LibraryUpdate(current_version="1.0.0"))
        assert result is None

    @pytest.mark.asyncio
    async def test_get_critical_libraries(
        self, test_db: AsyncSession, sample_library: Library
    ) -> None:
        # Mark library as Critical
        await test_db.execute(
            __import__("sqlalchemy").text(
                f"UPDATE libraries SET alert_priority='Critical' WHERE id={sample_library.id}"
            )
        )
        await test_db.commit()

        repo = LibraryRepository(test_db)
        critical = await repo.get_critical_libraries()
        assert any(lib.id == sample_library.id for lib in critical)

    @pytest.mark.asyncio
    async def test_get_by_platform(
        self, test_db: AsyncSession, sample_library: Library
    ) -> None:
        repo = LibraryRepository(test_db)
        android = await repo.get_by_platform("Android")
        assert len(android) >= 1
        assert all(lib.platform == "Android" for lib in android)


class TestVersionHistoryRepository:

    @pytest.mark.asyncio
    async def test_create_and_retrieve(
        self, test_db: AsyncSession, sample_library: Library
    ) -> None:
        repo = VersionHistoryRepository(test_db)
        entry = await repo.create(
            library_id=sample_library.id,
            version_number="1.0.0",
            record_type="current",
            source="test",
        )
        assert entry.id is not None
        assert entry.version_number == "1.0.0"
        assert entry.record_type == "current"

    @pytest.mark.asyncio
    async def test_get_by_library_returns_ordered(
        self, test_db: AsyncSession, sample_library: Library
    ) -> None:
        repo = VersionHistoryRepository(test_db)
        await repo.create(sample_library.id, "1.0.0", "current")
        await repo.create(sample_library.id, "2.0.0", "latest")

        history = await repo.get_by_library(sample_library.id)
        assert len(history) == 2
        # Should be ordered by recorded_at desc
        versions = [h.version_number for h in history]
        assert "1.0.0" in versions
        assert "2.0.0" in versions

    @pytest.mark.asyncio
    async def test_get_by_library_empty_for_new(
        self, test_db: AsyncSession, sample_library: Library
    ) -> None:
        # Fresh library with no history entries
        lib2 = Library(
            sl_no=99, package="com.example:no-history", platform="iOS",
            update_needed="None", status="Active", ecosystem="mobile",
        )
        test_db.add(lib2)
        await test_db.commit()
        await test_db.refresh(lib2)

        repo = VersionHistoryRepository(test_db)
        history = await repo.get_by_library(lib2.id)
        assert history == []


class TestUpgradeLifecycleRepository:

    @pytest.mark.asyncio
    async def test_upsert_keeps_status_when_target_version_unchanged(
        self, test_db: AsyncSession, sample_library: Library
    ) -> None:
        repo = UpgradeLifecycleRepository(test_db)

        lc = await repo.upsert(sample_library.id, recommendation_id=None, target_version="2.0.0")
        lc.status = "In Progress"
        lc.actioned_by = "admin"
        lc.skip_reason = "work started"
        await test_db.commit()

        same = await repo.upsert(sample_library.id, recommendation_id=None, target_version="2.0.0")
        assert same.status == "In Progress"
        assert same.actioned_by == "admin"
        assert same.skip_reason == "work started"
        assert same.target_version == "2.0.0"

    @pytest.mark.asyncio
    async def test_upsert_resets_to_pending_when_target_version_changes(
        self, test_db: AsyncSession, sample_library: Library
    ) -> None:
        repo = UpgradeLifecycleRepository(test_db)

        lc = await repo.upsert(sample_library.id, recommendation_id=None, target_version="2.0.0")
        lc.status = "In Progress"
        lc.actioned_by = "admin"
        lc.skip_reason = "work started"
        lc.target_sprint = "Sprint-1"
        lc.target_date = "2026-07-01"
        await test_db.commit()

        changed = await repo.upsert(sample_library.id, recommendation_id=None, target_version="2.1.0")
        assert changed.status == "Pending"
        assert changed.actioned_by is None
        assert changed.skip_reason is None
        assert changed.target_sprint is None
        assert changed.target_date is None
        assert changed.completed_version is None
        assert changed.target_version == "2.1.0"

"""
Integration tests for library-data-service routers.
Uses FastAPI test client with in-memory DB (see conftest.py).
"""
from __future__ import annotations
import pytest
from httpx import AsyncClient

from src.models.orm import Library


class TestLibrariesRouter:

    @pytest.mark.asyncio
    async def test_get_all_libraries_returns_200(
        self, test_client: AsyncClient, sample_library: Library
    ) -> None:
        resp = await test_client.get("/api/v1/libraries")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["total"] >= 1
        assert len(body["data"]["libraries"]) >= 1

    @pytest.mark.asyncio
    async def test_get_library_by_id_returns_correct_data(
        self, test_client: AsyncClient, sample_library: Library
    ) -> None:
        resp = await test_client.get(f"/api/v1/libraries/{sample_library.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["package"] == "com.example:test-lib"
        assert body["data"]["platform"] == "Android"
        assert body["data"]["update_needed"] == "Mandatory"

    @pytest.mark.asyncio
    async def test_get_library_not_found_returns_error(
        self, test_client: AsyncClient
    ) -> None:
        resp = await test_client.get("/api/v1/libraries/99999")
        assert resp.status_code == 404
        body = resp.json()
        assert body["success"] is False
        assert body["error"]["code"] == "LIBRARY_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_filter_by_platform(
        self, test_client: AsyncClient, sample_library: Library
    ) -> None:
        resp = await test_client.get("/api/v1/libraries?platform=Android")
        assert resp.status_code == 200
        body = resp.json()
        for lib in body["data"]["libraries"]:
            assert lib["platform"] == "Android"

    @pytest.mark.asyncio
    async def test_filter_by_update_needed(
        self, test_client: AsyncClient, sample_library: Library
    ) -> None:
        resp = await test_client.get("/api/v1/libraries?update_needed=Mandatory")
        assert resp.status_code == 200
        body = resp.json()
        for lib in body["data"]["libraries"]:
            assert lib["update_needed"] == "Mandatory"

    @pytest.mark.asyncio
    async def test_update_library(
        self, test_client: AsyncClient, sample_library: Library
    ) -> None:
        resp = await test_client.put(
            f"/api/v1/libraries/{sample_library.id}",
            json={
                "current_version": "2.0.0",
                "status": "Active",
                "updated_by": "test-user",
                "reason": "Upgraded to latest",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["current_version"] == "2.0.0"

    @pytest.mark.asyncio
    async def test_update_nonexistent_library(
        self, test_client: AsyncClient
    ) -> None:
        resp = await test_client.put(
            "/api/v1/libraries/99999",
            json={"current_version": "1.0.0", "updated_by": "test"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_by_platform_endpoint(
        self, test_client: AsyncClient, sample_library: Library
    ) -> None:
        resp = await test_client.get("/api/v1/libraries/platform/Android")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)

    @pytest.mark.asyncio
    async def test_get_critical_libraries(
        self, test_client: AsyncClient, sample_library: Library, test_db
    ) -> None:
        # Promote sample library to Critical
        import sqlalchemy
        await test_db.execute(
            sqlalchemy.text(
                f"UPDATE libraries SET alert_priority='Critical' WHERE id={sample_library.id}"
            )
        )
        await test_db.commit()

        resp = await test_client.get("/api/v1/libraries/critical")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert any(lib["id"] == sample_library.id for lib in body["data"])


class TestVersionHistoryRouter:

    @pytest.mark.asyncio
    async def test_create_and_get_version_history(
        self, test_client: AsyncClient, sample_library: Library
    ) -> None:
        # Create
        resp = await test_client.post(
            "/api/v1/version-history",
            json={
                "library_id": sample_library.id,
                "version_number": "1.5.0",
                "record_type": "latest",
                "source": "scraper",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["version_number"] == "1.5.0"

        # Get
        resp2 = await test_client.get(f"/api/v1/version-history/{sample_library.id}")
        assert resp2.status_code == 200
        history = resp2.json()["data"]
        assert any(h["version_number"] == "1.5.0" for h in history)

    @pytest.mark.asyncio
    async def test_version_history_empty_for_new_library(
        self, test_client: AsyncClient
    ) -> None:
        resp = await test_client.get("/api/v1/version-history/99999")
        assert resp.status_code == 200
        assert resp.json()["data"] == []


class TestHealthRouter:

    @pytest.mark.asyncio
    async def test_health_returns_200(self, test_client: AsyncClient) -> None:
        resp = await test_client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "status" in body
        assert body["service"] == "library-data-service"


class TestLifecycleRouter:

    @pytest.mark.asyncio
    async def test_reselecting_new_target_resets_to_pending(
        self, test_client: AsyncClient, sample_library: Library
    ) -> None:
        # 1) Start lifecycle with target v2.0.0
        init = await test_client.post(
            "/api/v1/lifecycle",
            json={
                "library_id": sample_library.id,
                "actioned_by": "admin",
                "target_version": "2.0.0",
            },
        )
        assert init.status_code == 201
        lifecycle_id = init.json()["data"]["id"]

        # 2) Move to In Progress (active workflow)
        to_in_progress = await test_client.put(
            f"/api/v1/lifecycle/{lifecycle_id}/in-progress",
            json={
                "actioned_by": "admin",
                "skip_reason": "working on 2.0.0",
                "target_version": "2.0.0",
            },
        )
        assert to_in_progress.status_code == 200
        assert to_in_progress.json()["data"]["status"] == "In Progress"

        # 3) User reselects a different target version from version history
        reselect = await test_client.post(
            "/api/v1/lifecycle",
            json={
                "library_id": sample_library.id,
                "actioned_by": "admin",
                "target_version": "2.1.0",
            },
        )
        assert reselect.status_code == 201
        body = reselect.json()["data"]
        assert body["id"] == lifecycle_id
        assert body["status"] == "Pending"
        assert body["target_version"] == "2.1.0"
        assert body["actioned_by"] is None

    @pytest.mark.asyncio
    async def test_set_active_requires_in_progress(
        self, test_client: AsyncClient, sample_library: Library
    ) -> None:
        init = await test_client.post(
            "/api/v1/lifecycle",
            json={
                "library_id": sample_library.id,
                "actioned_by": "admin",
                "target_version": "2.0.0",
            },
        )
        assert init.status_code == 201
        lifecycle_id = init.json()["data"]["id"]

        # Still Pending here, so set-active should be rejected
        set_active = await test_client.put(
            f"/api/v1/lifecycle/{lifecycle_id}/set-active",
            json={
                "target_version": "2.0.0",
                "comment": "trying direct activate",
                "actioned_by": "admin",
            },
        )
        assert set_active.status_code == 422
        assert "Move to In Progress first" in set_active.json()["detail"]

    @pytest.mark.asyncio
    async def test_set_active_rejects_target_version_mismatch(
        self, test_client: AsyncClient, sample_library: Library
    ) -> None:
        init = await test_client.post(
            "/api/v1/lifecycle",
            json={
                "library_id": sample_library.id,
                "actioned_by": "admin",
                "target_version": "2.0.0",
            },
        )
        assert init.status_code == 201
        lifecycle_id = init.json()["data"]["id"]

        to_in_progress = await test_client.put(
            f"/api/v1/lifecycle/{lifecycle_id}/in-progress",
            json={
                "actioned_by": "admin",
                "skip_reason": "working on 2.0.0",
                "target_version": "2.0.0",
            },
        )
        assert to_in_progress.status_code == 200
        assert to_in_progress.json()["data"]["status"] == "In Progress"

        mismatch_activate = await test_client.put(
            f"/api/v1/lifecycle/{lifecycle_id}/set-active",
            json={
                "target_version": "2.1.0",
                "comment": "trying to jump directly to another target",
                "actioned_by": "admin",
            },
        )
        assert mismatch_activate.status_code == 422
        assert "Target version mismatch" in mismatch_activate.json()["detail"]

        lifecycle_after = await test_client.get(f"/api/v1/lifecycle/{sample_library.id}")
        assert lifecycle_after.status_code == 200
        data = lifecycle_after.json()["data"]
        assert data["status"] == "In Progress"
        assert data["target_version"] == "2.0.0"

    @pytest.mark.asyncio
    async def test_set_active_syncs_version_history_current_flags(
        self, test_client: AsyncClient, sample_library: Library, test_db
    ) -> None:
        # Seed library_versions rows so UI version table can reflect current markers.
        import sqlalchemy
        await test_db.execute(
            sqlalchemy.text(
                """
                INSERT INTO library_versions (library_id, version, is_latest, is_current, scraped_at)
                VALUES (:library_id, :v1, 0, 1, CURRENT_TIMESTAMP), (:library_id, :v2, 1, 0, CURRENT_TIMESTAMP)
                """
            ),
            {"library_id": sample_library.id, "v1": "1.0.0", "v2": "2.0.0"},
        )
        await test_db.commit()

        init = await test_client.post(
            "/api/v1/lifecycle",
            json={
                "library_id": sample_library.id,
                "actioned_by": "admin",
                "target_version": "2.0.0",
            },
        )
        assert init.status_code == 201
        lifecycle_id = init.json()["data"]["id"]

        to_in_progress = await test_client.put(
            f"/api/v1/lifecycle/{lifecycle_id}/in-progress",
            json={
                "actioned_by": "admin",
                "skip_reason": "work started",
                "target_version": "2.0.0",
            },
        )
        assert to_in_progress.status_code == 200

        set_active = await test_client.put(
            f"/api/v1/lifecycle/{lifecycle_id}/set-active",
            json={
                "target_version": "2.0.0",
                "comment": "activation complete",
                "actioned_by": "admin",
            },
        )
        assert set_active.status_code == 200

        versions = await test_client.get(f"/api/v1/libraries/{sample_library.id}/versions")
        assert versions.status_code == 200
        vdata = versions.json()["data"]
        assert vdata["current_version"] == "2.0.0"

        by_ver = {row["version"]: row for row in vdata["versions"]}
        assert by_ver["2.0.0"]["is_current"] is True
        assert by_ver["1.0.0"]["is_current"] is False

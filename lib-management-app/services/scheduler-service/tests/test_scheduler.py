"""
Tests for scheduler-service — all downstream HTTP calls mocked.
"""
from __future__ import annotations
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from src.models.schemas import PipelineStatus, StepName
from src.services.scheduler_service import SchedulerService, _run_history


# ── Sample pipeline context ───────────────────────────────────────────────────

_LIBS = [
    {"id": 1, "package": "androidx.core:core-ktx", "platform": "Android",
     "current_version": "1.12.0", "latest_version": "1.15.0",
     "update_needed": "Mandatory", "status": "Active", "registry": "maven"},
    {"id": 2, "package": "Alamofire", "platform": "iOS",
     "current_version": "5.9.1", "latest_version": "5.12.0",
     "update_needed": "Recommended", "status": "Active", "registry": "cocoapods"},
]


# ── Pipeline step unit tests ──────────────────────────────────────────────────

class TestPipelineSteps:

    @pytest.mark.asyncio
    async def test_fetch_libraries_success(self):
        from src.pipeline.steps import step_fetch_libraries
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"data": {"libraries": _LIBS}}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock,
                   return_value=mock_resp):
            ctx: dict = {}
            result = await step_fetch_libraries(ctx)

        assert result.status == PipelineStatus.COMPLETED
        assert result.items_processed == 2
        assert ctx["libraries"] == _LIBS

    @pytest.mark.asyncio
    async def test_fetch_libraries_failure(self):
        from src.pipeline.steps import step_fetch_libraries
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock,
                   side_effect=Exception("Connection refused")):
            ctx: dict = {}
            result = await step_fetch_libraries(ctx)

        assert result.status == PipelineStatus.FAILED
        assert "Connection refused" in result.message

    @pytest.mark.asyncio
    async def test_batch_scrape_no_libraries_fails(self):
        from src.pipeline.steps import step_batch_scrape
        result = await step_batch_scrape({})
        assert result.status == PipelineStatus.FAILED

    @pytest.mark.asyncio
    async def test_batch_scrape_skips_libs_without_registry(self):
        from src.pipeline.steps import step_batch_scrape
        libs_no_registry = [{"id": 1, "package": "SomeLib", "platform": "iOS"}]
        result = await step_batch_scrape({"libraries": libs_no_registry})
        assert result.status == PipelineStatus.COMPLETED
        assert "skipped" in result.message.lower()

    @pytest.mark.asyncio
    async def test_batch_compare_success(self):
        from src.pipeline.steps import step_batch_compare
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "data": {"results": [{"library_id": 1, "version_status": "newer",
                                  "new_version_released": True}], "newer_count": 1}
        }
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock,
                   return_value=mock_resp):
            ctx = {"libraries": _LIBS}
            result = await step_batch_compare(ctx)

        assert result.status == PipelineStatus.COMPLETED
        assert "comparison_results" in ctx

    @pytest.mark.asyncio
    async def test_batch_recommend_success(self):
        from src.pipeline.steps import step_batch_recommend
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "data": {"results": [{"library_id": 1, "upgrade_recommended": "Yes",
                                  "recommendation_summary": "Upgrade now"}],
                     "yes_count": 1}
        }
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock,
                   return_value=mock_resp):
            ctx = {"libraries": _LIBS, "comparison_results": []}
            result = await step_batch_recommend(ctx)

        assert result.status == PipelineStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_notify_success(self):
        from src.pipeline.steps import step_notify
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"data": {"skipped_by_dedup": False}}
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock,
                   return_value=mock_resp):
            ctx = {"libraries": _LIBS, "recommendation_results": []}
            result = await step_notify(ctx)

        assert result.status == PipelineStatus.COMPLETED


# ── Scheduler service unit tests ──────────────────────────────────────────────

class TestSchedulerService:

    @pytest.mark.asyncio
    async def test_run_pipeline_all_steps_mocked(self):
        from src.models.schemas import StepResult
        from datetime import datetime, timezone

        mock_step = AsyncMock(return_value=StepResult(
            step=StepName.FETCH_LIBRARIES,
            status=PipelineStatus.COMPLETED,
            message="ok", items_processed=2,
        ))
        mock_step_ok = AsyncMock(return_value=StepResult(
            step=StepName.BATCH_SCRAPE,
            status=PipelineStatus.COMPLETED, message="ok",
        ))

        svc = SchedulerService()
        with patch("src.services.scheduler_service.step_fetch_libraries",
                   AsyncMock(return_value=StepResult(step=StepName.FETCH_LIBRARIES,
                                                      status=PipelineStatus.COMPLETED,
                                                      message="ok", items_processed=2))), \
             patch("src.services.scheduler_service.step_batch_scrape",
                   AsyncMock(return_value=StepResult(step=StepName.BATCH_SCRAPE,
                                                      status=PipelineStatus.COMPLETED, message="ok"))), \
             patch("src.services.scheduler_service.step_fetch_version_history",
                 AsyncMock(return_value=StepResult(step=StepName.FETCH_VERSION_HISTORY,
                                        status=PipelineStatus.COMPLETED, message="ok"))), \
             patch("src.services.scheduler_service.step_batch_compare",
                   AsyncMock(return_value=StepResult(step=StepName.BATCH_COMPARE,
                                                      status=PipelineStatus.COMPLETED, message="ok"))), \
             patch("src.services.scheduler_service.step_batch_recommend",
                   AsyncMock(return_value=StepResult(step=StepName.BATCH_RECOMMEND,
                                                      status=PipelineStatus.COMPLETED, message="ok"))), \
             patch("src.services.scheduler_service.step_check_deadlines",
                   AsyncMock(return_value=StepResult(step=StepName.CHECK_DEADLINES,
                                                      status=PipelineStatus.COMPLETED, message="0 overdue, 0 warning"))), \
             patch("src.services.scheduler_service.step_notify",
                   AsyncMock(return_value=StepResult(step=StepName.NOTIFY,
                                                      status=PipelineStatus.COMPLETED, message="ok"))):
            run = await svc.run_pipeline(triggered_by="test")

        assert run.status == PipelineStatus.COMPLETED
        assert len(run.steps) == 7

    @pytest.mark.asyncio
    async def test_pipeline_aborts_on_fetch_failure(self):
        from src.models.schemas import StepResult
        svc = SchedulerService()
        with patch("src.services.scheduler_service.step_fetch_libraries",
                   AsyncMock(return_value=StepResult(step=StepName.FETCH_LIBRARIES,
                                                      status=PipelineStatus.FAILED,
                                                      message="connection refused"))):
            run = await svc.run_pipeline()

        assert run.status == PipelineStatus.FAILED
        assert len(run.steps) == 1   # only fetch step ran

    @pytest.mark.asyncio
    async def test_concurrent_run_rejected(self):
        import src.services.scheduler_service as svc_mod
        svc_mod._pipeline_running = True
        svc = SchedulerService()
        run = await svc.run_pipeline()
        assert run.status == PipelineStatus.FAILED
        assert "already running" in (run.error or "").lower()

    def test_get_schedule_returns_config(self):
        svc = SchedulerService()
        cfg = svc.get_schedule()
        assert cfg.cron == settings.schedule_cron

    @pytest.mark.asyncio
    async def test_update_schedule_changes_cron(self):
        from src.models.schemas import ScheduleUpdateRequest
        svc = SchedulerService()
        # Start the scheduler within the running event loop
        svc._scheduler.start()
        try:
            req = ScheduleUpdateRequest(cron="0 9 * * *", enabled=True)
            cfg = svc.update_schedule(req)
            assert cfg.cron == "0 9 * * *"
        finally:
            svc.shutdown()


# ── Router integration tests ──────────────────────────────────────────────────

class TestHealthRouter:
    @pytest.mark.asyncio
    async def test_health_returns_200(self, test_client):
        resp = await test_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


class TestScheduleRouter:
    @pytest.mark.asyncio
    async def test_get_schedule_returns_config(self, test_client):
        resp = await test_client.get("/api/v1/schedule")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "cron" in data
        assert "enabled" in data

    @pytest.mark.asyncio
    async def test_update_schedule(self, test_client):
        resp = await test_client.put(
            "/api/v1/schedule",
            json={"cron": "0 10 * * 1-5", "enabled": False},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["cron"] == "0 10 * * 1-5"
        assert resp.json()["data"]["enabled"] is False


class TestRunsRouter:
    @pytest.mark.asyncio
    async def test_list_runs_empty_initially(self, test_client):
        resp = await test_client.get("/api/v1/runs")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    @pytest.mark.asyncio
    async def test_get_run_not_found(self, test_client):
        resp = await test_client.get("/api/v1/runs/nonexistent-id")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_run_now_returns_run_id(self, test_client):
        resp = await test_client.post("/api/v1/run/now")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "run_id" in data
        assert data["triggered_by"] == "manual"

    @pytest.mark.asyncio
    async def test_get_run_after_trigger(self, test_client):
        run_resp = await test_client.post("/api/v1/run/now")
        run_id = run_resp.json()["data"]["run_id"]
        resp = await test_client.get(f"/api/v1/runs/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["run_id"] == run_id


from src.config import settings

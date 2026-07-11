"""Scheduler Service — configuration."""
from __future__ import annotations
from pydantic import Field
from shared.config.base_settings import ServiceSettings


class Settings(ServiceSettings):
    service_name: str = "scheduler-service"
    service_version: str = "1.0.0"

    # ── Upstream services ─────────────────────────────────────────────────────
    library_data_service_url: str = Field(default="http://library-data-service:8001")
    scraper_service_url: str = Field(default="http://scraper-service:8002")
    comparison_service_url: str = Field(default="http://comparison-service:8003")
    recommendation_service_url: str = Field(default="http://recommendation-service:8004")
    notification_service_url: str = Field(default="http://notification-service:8005")

    # ── APScheduler ───────────────────────────────────────────────────────────
    # Default cron: Mon–Fri at 08:00 UTC
    schedule_cron: str = Field(
        default="0 8 * * 1-5",
        description="Cron expression for the pipeline schedule",
    )
    schedule_enabled: bool = True

    # ── Pipeline limits ───────────────────────────────────────────────────────
    pipeline_max_libraries: int = 1000
    # HTTP timeout for each downstream service call (seconds)
    pipeline_step_timeout: float = 120.0


settings = Settings()
